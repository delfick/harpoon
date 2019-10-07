from harpoon.errors import NoSuchImage, BadImage, HarpoonError
from harpoon.ship.runner import ContainerRunner, Runner
from harpoon.option_spec import image_specs
from harpoon.option_spec import image_objs
from harpoon.ship.builder import Builder

from http.server import HTTPServer, BaseHTTPRequestHandler
from docker.errors import APIError as DockerAPIError
from delfick_project.norms import dictobj, sb, Meta
from delfick_project.errors import DelfickError
from delfick_project.logging import lc
from threading import Event, Lock
import socketserver
import logging
import socket
import time
import json

log = logging.getLogger("harpoon.container_manager")


class BadJSON(HarpoonError):
    desc = "JSON was invalid"


class BadRequest(HarpoonError):
    desc = "Request was invalid"


class FailedToWaitForServer(HarpoonError):
    desc = "Timed out waiting for the container manager to start"


class ImageAlreadyFailed(HarpoonError):
    desc = "Already attempted to start image and that failed"


class ShuttingDown(HarpoonError):
    desc = "The container manager is shutting down"


class StartContainerRequest(dictobj.Spec):
    image = dictobj.Field(sb.string_spec, wrapper=sb.required)
    ports = dictobj.Field(
        sb.listof(image_specs.port_spec(), expect=image_objs.Port), wrapper=sb.required
    )
    lock = dictobj.Field(sb.boolean, default=False)


class StopContainerRequest(dictobj.Spec):
    image = dictobj.Field(sb.string_spec, wrapper=sb.required)


class UnlockContainerRequest(dictobj.Spec):
    image = dictobj.Field(sb.string_spec, wrapper=sb.required)


def port_connected(port):
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False


def wait_for_server(port):
    start = time.time()
    while time.time() - start < 3:
        if port_connected(port):
            return
        time.sleep(0.1)

    if not port_connected(port):
        raise FailedToWaitForServer(port=port)


class ContainerInfo:
    """
    Information about a running container

    Contains a lock that says we're already building

    A switch that says if we've already tried to build before and it didn't work

    And events that says this container is in use and waiting for it to be unlocked.
    """

    def __init__(self):
        self.lock = Lock()
        self.building = None
        self.use_events = []
        self.failed_already = False

    def force_unlock(self):
        """Used by shutdown to making all the events set"""
        with self.lock:
            if self.building:
                self.building.set()

            for event in self.use_events:
                event.set()

    def wait_for_running(self):
        """Wait for any existing /start_container calls to finish"""
        with self.lock:
            if self.failed_already:
                raise ImageAlreadyFailed()

            if self.building is None:
                self.building = Event()
                return

            building = self.building

        building.wait()

    def failed_running(self):
        """Mark this container as failed to have been built and started"""
        with self.lock:
            self.failed_already = True
            self.building.set()

    def success_running(self):
        """Mark this container as having succeeded to have been build and started"""
        with self.lock:
            self.building.set()

    def wait_for_lock(self):
        """Wait for any existing holders of the container to be finished"""
        with self.lock:
            event = Event()
            events = list(self.use_events)
            self.use_events.append(event)

        for e in events:
            e.wait()

    def unlock(self):
        """
        Allow the next user of the container to use the container.

        We do this by removing the first event from our use_events array and
        setting it. Any existing /start_container calls will then proceed to
        start waiting on the next event.
        """
        with self.lock:
            if self.use_events:
                event = self.use_events.pop(0)
                event.set()


class Manager:
    def __init__(self, harpoon, images, image_puller):
        self.images = images
        self.harpoon = harpoon
        self.runners = {}
        self.image_puller = image_puller

        self.pulled = set()
        self.shutting_down = False

        self.stop_container_spec = StopContainerRequest.FieldSpec()
        self.start_container_spec = StartContainerRequest.FieldSpec()
        self.unlock_container_spec = UnlockContainerRequest.FieldSpec()

        self.info_lock = Lock()
        self.info = {}

    def version(self, request):
        from harpoon import VERSION

        request.send_response(200)
        request.end_headers()
        request.wfile.write("harpoon {0}".format(VERSION).encode())

    def shutdown(self, request):
        self.shutting_down = True
        log.info("Stopping the manager")

        with self.info_lock:
            for info in self.info.values():
                info.force_unlock()

        for image, runner in self.runners.items():
            try:
                log.info("Stopping container for {0}".format(image))
                runner.finish(force=True)
            except Exception as error:
                log.exception("Failed to stop a container\terror=%s", error)
        request.send_response(204)
        request.end_headers()
        request.server.shutdown()

    def start_container(self, request):
        options, image = self._make_options(request, self.start_container_spec)

        with self.info_lock:
            if options.image not in self.info:
                self.info[options.image] = ContainerInfo()
            info = self.info[options.image]

        info.wait_for_running()

        just_created = False
        try:
            if options.image not in self.runners:
                just_created = True
                self._build_and_run(options, image)
        except:
            info.failed_running()
            raise
        finally:
            info.success_running()

        if options.lock:
            if self.shutting_down:
                raise ShuttingDown()

            log.info(lc("Waiting for lock for container", image=options.image))
            info.wait_for_lock()

        self._send_container_info(request, image, just_created)

    def _build_and_run(self, options, image):
        image.ports = options.ports
        self._pull_external(image)

        Builder().make_image(image, self.images)

        runner = ContainerRunner(Runner(), self.images[options.image], self.images, detach=True)
        self.runners[options.image] = runner

        container_id = None

        try:
            runner.start()

            class FakeConf:
                harpoon = image.harpoon
                dependency_options = sb.NotSpecified

                def dependency_images(self):
                    yield options.image, None

            container_id = runner.conf.container_id
            Runner().wait_for_deps(FakeConf(), self.images)
        except Exception as error:
            if not isinstance(error, DockerAPIError):
                log.exception("Unexpected error starting container\terror=%s", error)

            try:
                if container_id:
                    runner.conf.container_id = container_id

                runner.finish(force=True)
            except Exception as e:
                log.error("Failed to make sure image was cleaned up\terror=%s", e)
            finally:
                del self.runners[options.image]

            raise BadImage("Failed to start the container", error=error)

    def unlock_container(self, request):
        options, image = self._make_options(request, self.unlock_container_spec)

        with self.info_lock:
            if options.image not in self.info:
                request.send_response(204)
                request.end_headers()
                return
            info = self.info[options.image]

        log.info(lc("Unlocking container", image=options.image))
        info.unlock()
        request.send_response(204)
        request.end_headers()

    def stop_container(self, request):
        options, image = self._make_options(request, self.stop_container_spec)
        if options.image in self.runners:
            self.runners[options.image].finish(force=True)
            del self.runners[options.image]
        request.send_response(204)
        request.end_headers()

    def _make_options(self, request, spec):
        meta = Meta.empty().at("<request>")

        content_length = request.headers["Content-Length"]
        if not content_length or int(content_length) <= 0:
            raise BadRequest("Expected a request body")

        content_type = request.headers["Content-Type"]
        if content_type != "application/json":
            raise BadRequest(
                "Expected to receive json, but content_type was not application/json",
                got=content_type,
            )

        try:
            content = request.rfile.read(int(content_length))
            if isinstance(content, bytes):
                content = content.decode()
            j = json.loads(content)
        except (TypeError, ValueError) as error:
            raise BadJSON(reason=error)

        options = spec.normalise(meta, j)
        if options.image not in self.images:
            raise NoSuchImage(wanted=options.image, available=sorted(self.images))

        image = self.images[options.image]

        return options, image

    def _send_container_info(self, request, image, just_created):
        info = self.harpoon.docker_api.inspect_container(image.container_id)

        ports = info["NetworkSettings"]["Ports"]
        port_map = {}
        for key, vals in ports.items():
            if vals:
                port = key.split("/", 1)[0]
                port_map[int(port)] = int(vals[0]["HostPort"])

        request.send_response(200)
        request.send_header("Content-Type", "application/json")
        request.end_headers()

        p = {"ports": port_map, "just_created": just_created, "container_id": image.container_id}
        request.wfile.write(json.dumps(p).encode())

    def _pull_external(self, image):
        deps = set()
        for dep in image.commands.external_dependencies:
            deps.add(dep)

        for dep in sorted(deps):
            if dep in self.pulled:
                continue
            log.info(lc("Pulling image", image=dep))
            self.image_puller(image=dep)
            self.pulled.add(dep)


def make_server(manager, address):
    class RequestHandler(BaseHTTPRequestHandler):
        def handle(self):
            try:
                super().handle()
            except KeyboardInterrupt:
                raise
            except Exception as error:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()

                if isinstance(error, DelfickError):
                    asdct = error.as_dict()
                else:
                    log.exception("Unexpected error")
                    asdct = {"message": str(error)}

                e = {"error": asdct, "error_code": error.__class__.__name__}
                self.wfile.write(json.dumps(e, default=lambda o: repr(o)).encode())

        def do_GET(self):
            if self.path == "/version":
                manager.version(self)
            elif self.path == "/shutdown":
                if manager.shutting_down:
                    self.send_response(204)
                    self.end_headers()
                else:
                    manager.shutdown(self)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write("Unknown path: {0}".format(self.path).encode())

        def do_POST(self):
            if self.path == "/stop_container":
                manager.stop_container(self)
            elif self.path == "/start_container":
                manager.start_container(self)
            elif self.path == "/unlock_container":
                manager.unlock_container(self)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write("Unknown path: {0}".format(self.path).encode())

        def log_message(self, format, *args):
            log.info("%s - %s", self.address_string(), format % args)

    class Server(socketserver.ThreadingMixIn, HTTPServer):
        pass

    return Server(address, RequestHandler)


__all__ = ["make_server", "Manager"]
