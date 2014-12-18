from __future__ import print_function

from harpoon.errors import NoSuchKey, BadOption, NoSuchImage, BadCommand, BadImage, ProgrammerError, FailedImage, BadResult, UserQuit
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.helpers import until
from harpoon.layers import Layers

from docker.errors import APIError as DockerAPIError
from input_algorithms.spec_base import NotSpecified
from option_merge.joiner import dot_joiner
from option_merge import MergedOptions
from contextlib import contextmanager
import dockerpty
import humanize
import logging
import socket
import json
import uuid
import sys
import os

log = logging.getLogger("harpoon.imager")

class Image(object):
    def __init__(self, name, configuration, path, docker_context):
        self.name = name
        self.path = path
        self.configuration = configuration
        self.docker_context = docker_context
        self.already_running = False

    @property
    def parent_dir(self):
        return self.image_configuration.context.parent_dir

    @property
    def harpoon(self):
        if getattr(self, "_harpoon", None) is None:
            self._harpoon = self.configuration["harpoon"]
        return self._harpoon

    @property
    def dependencies(self):
        return self.image_configuration.dependencies

    @property
    def image_configuration(self):
        if getattr(self, "_image_configuration", None) is None:
            self._image_configuration = self.configuration[self.path]
        return self._image_configuration

    @property
    def mtime(self):
        if not getattr(self, "_mtime", None):
            val = self.configuration.get("__mtime__")
            if callable(val):
                val = val()
            if val is not None:
                val = int(val)
            self._mtime = val
        return self._mtime

    @property
    def container_id(self):
        """Find a container id"""
        if getattr(self, "_container_id", None):
            return self._container_id

        try:
            containers = self.docker_context.containers(all=True)
        except ValueError:
            log.warning("Failed to get a list of active docker files")
            containers = []

        self._container_id = None
        for container in containers:
            if any(name in container.get("Names", []) for name in (self.image_configuration.container_name, "/{0}".format(self.image_configuration.container_name))):
                self._container_id = container["Id"]
                break

        return self._container_id

    def push(self):
        """Push this image"""
        self.push_or_pull("push")

    def pull(self, ignore_missing=False):
        """Push this image"""
        self.push_or_pull("pull", ignore_missing=ignore_missing)

    def push_or_pull(self, action=None, ignore_missing=False):
        """Push or pull this image"""
        if action not in ("push", "pull"):
            raise ProgrammerError("Should have called push_or_pull with action to either push or pull, got {0}".format(action))

        if not self.image_configuration.image_index:
            raise BadImage("Can't push without an image_index configuration", image=self.name)
        for line in getattr(self.docker_context, action)(self.image_configuration.image_name, stream=True):
            line_detail = None
            try:
                line_detail = json.loads(line)
            except (ValueError, TypeError) as error:
                log.warning("line from docker wasn't json", got=line, error=error)

            if line_detail:
                if "errorDetail" in line_detail:
                    msg = line_detail["errorDetail"].get("message", line_detail["errorDetail"])
                    if ignore_missing and action == "pull":
                        log.error("Failed to %s an image\timage=%s\timage_name=%s\tmsg=%s", action, self.name, self.image_configuration.image_name, msg)
                    else:
                        raise FailedImage("Failed to {0} an image".format(action), image=self.name, image_name=self.image_configuration.image_name, msg=msg)
                if "status" in line_detail:
                    line = line_detail["status"].strip()

                if "progressDetail" in line_detail:
                    line = "{0} {1}".format(line, line_detail["progressDetail"])

                if "progress" in line_detail:
                    line = "{0} {1}".format(line, line_detail["progress"])

            if line_detail and ("progressDetail" in line_detail or "progress" in line_detail):
                sys.stdout.write("\r{0}".format(line))
                sys.stdout.flush()
            else:
                print(line)

    def run_container(self, images, detach=False, started=None, dependency=False):
        """Run this image and all dependency images"""
        if self.already_running:
            return

        try:
            for dependency_name, detached in self.image_configuration.dependency_images(images, ignore_parent=True):
                try:
                    images[dependency_name].run_container(images, detach=detached, dependency=True)
                except Exception as error:
                    raise BadImage("Failed to start dependency container", image=self.name, dependency=dependency_name, error=error)

            tty = not detach and self.harpoon.interactive
            env = dict(e.pair() for e in self.image_configuration.env)
            links = [link.pair() for link in self.image_configuration.links]
            ports = dict([port.pair() for port in self.image_configuration.ports])
            volumes = self.image_configuration.volumes.mount_options()
            command = self.image_configuration.formatted_command
            volumes_from = list(self.image_configuration.volumes.share_with_names)

            self._run_container(self.name, self.image_configuration.image_name, self.image_configuration.container_name
                , detach=detach, command=command, tty=tty, env=env, ports=ports
                , volumes=volumes, volumes_from=volumes_from, links=links, dependency=dependency
                )

        finally:
            if not detach and not dependency:
                for dependency, _ in self.image_configuration.dependency_images(images, ignore_parent=True):
                    try:
                        images[dependency].stop_container(fail_on_bad_exit=True, fail_reason="Failed to run dependency container")
                    except BadImage:
                        raise
                    except Exception as error:
                        log.warning("Failed to stop dependency container\timage=%s\tdependency=%s\tcontainer_name=%s\terror=%s", self.name, dependency, images[dependency].container_name, error)
                self.stop_container()

    def _run_container(self, name, image_name, container_name
            , detach=False, command=None, tty=True, volumes=None, volumes_from=None, links=None, delete_on_exit=False, env=None, ports=None, dependency=False, no_intervention=False
            ):
        """Run a single container"""
        if not detach and dependency:
            tty = True
        log.info("Creating container from %s\timage=%s\tcontainer_name=%s\ttty=%s", image_name, name, container_name, tty)

        binds = {}
        volume_names = []
        if volumes is None:
            volumes = []

        uncreated = []
        for volume in volumes:
            if ":" in volume:
                name, bound = volume.split(":", 1)
                permissions = "rw"
                if ":" in bound:
                    bound, permissions = bound.split(":", 1)
                binds[name] = {"bind": bound, permissions: True}
                volume_names.append(bound)
                if not os.path.exists(name):
                    log.info("Making volume for mounting\tvolume=%s", name)
                    try:
                        os.makedirs(name)
                    except OSError as error:
                        uncreated.append((name, error))
        if uncreated:
            raise BadOption("Failed to create some volumes on the host", uncreated=uncreated)

        if volumes:
            log.info("\tUsing volumes\tvolumes=%s", volumes)

        if env:
            log.info("\tUsing environment\tenv=%s", sorted(env.keys()))
        if ports:
            log.info("\tUsing ports\tports=%s", ports.keys())
        container = self.docker_context.create_container(image_name
            , name=container_name
            , detach=detach
            , command=command
            , volumes=volumes
            , environment=env

            , tty = tty
            , ports = [port.container_port.port_pair for port in self.image_configuration.ports]
            , stdin_open = tty
            )

        container_id = container
        if isinstance(container_id, dict):
            if "errorDetail" in container_id:
                raise BadImage("Failed to create container", image=name, error=container_id["errorDetail"])
            container_id = container_id["Id"]
        self._container_id = container_id
        self.already_running = True

        try:
            log.info("Starting container %s", container_name)
            if links:
                log.info("\tLinks: %s", links)
            if volumes_from:
                log.info("\tVolumes from: %s", volumes_from)
            if ports:
                log.info("\tPort Bindings: %s", ports)

            self.docker_context.start(container_id
                , links = links
                , binds = binds
                , volumes_from = volumes_from
                , port_bindings = ports
                )

            if not detach and not dependency:
                try:
                    dockerpty.start(self.docker_context, container_id, interactive=tty)
                except KeyboardInterrupt:
                    pass

            inspection = None
            if not detach and not dependency:
                for _ in until(timeout=0.5, step=0.1, silent=True):
                    try:
                        inspection = self.docker_context.inspect_container(container_id)
                        if not isinstance(inspection, dict) or "State" not in inspection:
                            raise BadResult("Expected inspect result to be a dictionary with 'State' in it", found=inspection)
                        elif not inspection["State"]["Running"]:
                            break
                    except Exception as error:
                        log.error("Failed to see if container exited normally or not\thash=%s\terror=%s", container_id, error)

            if inspection and not no_intervention:
                if not inspection["State"]["Running"] and inspection["State"]["ExitCode"] != 0:
                    if self.harpoon.interactive and not self.harpoon.no_intervention:
                        print("!!!!")
                        print("Failed to run the container!")
                        print("Do you want commit the container in it's current state and /bin/bash into it to debug?")
                        answer = raw_input("[y]: ")
                        if not answer or answer.lower().startswith("y"):
                            with self.commit_and_run(container_id, command="/bin/bash"):
                                pass
                    raise BadImage("Failed to run container", container_id=container_id, container_name=container_name)
        finally:
            if delete_on_exit:
                self._stop_container(container_id, container_name)

    def stop_container(self, fail_on_bad_exit=False, fail_reason=None):
        """Stop this container if it exists"""
        container_id = self.container_id
        if container_id is None:
            return

        self._stop_container(container_id, self.image_configuration.container_name, fail_on_bad_exit=fail_on_bad_exit, fail_reason=fail_reason)
        self._container_id = None
        self.already_running = False

    def _stop_container(self, container_id, container_name, fail_on_bad_exit=False, fail_reason=None):
        """Stop some container"""
        stopped = False
        for _ in until(timeout=10):
            try:
                inspection = self.docker_context.inspect_container(container_id)
                if not isinstance(inspection, dict):
                    log.error("Weird response from inspecting the container\tresponse=%s", inspection)
                else:
                    if not inspection["State"]["Running"]:
                        stopped = True
                        break
                    else:
                        break
            except (socket.timeout, ValueError):
                log.warning("Failed to inspect the container\tcontainer_id=%s", container_id)
            except DockerAPIError as error:
                if error.response.status_code != 404:
                    raise
                else:
                    break

        if stopped:
            exit_code = inspection["State"]["ExitCode"]
            if exit_code != 0 and fail_on_bad_exit:
                if not self.harpoon.interactive:
                    print_logs = True
                else:
                    print("!!!!")
                    print("Container had already exited with a non zero exit code\tcontainer_name={0}\tcontainer_id={1}\texit_code={2}".format(container_name, container_id, exit_code))
                    print("Do you want to see the logs from this container?")
                    answer = raw_input("[y]: ")
                    print_logs = not answer or answer.lower().startswith("y")

                if print_logs:
                    print("=================== Logs for failed container {0} ({1})".format(container_id, container_name))
                    for line in self.docker_context.logs(container_id).split("\n"):
                        print(line)
                    print("------------------- End logs for failed container")
                fail_reason = fail_reason or "Failed to run container"
                raise BadImage(fail_reason, container_id=container_id, container_name=container_name)
        else:
            try:
                log.info("Killing container %s:%s", container_name, container_id)
                self.docker_context.kill(container_id, 9)
            except DockerAPIError:
                pass

            for _ in until(timeout=10, action="waiting for container to die\tcontainer_name={0}\tcontainer_id={1}".format(container_name, container_id)):
                try:
                    inspection = self.docker_context.inspect_container(container_id)
                    if not inspection["State"]["Running"]:
                        break
                except socket.timeout:
                    pass
                except ValueError:
                    log.warning("Failed to inspect the container\tcontainer_id=%s", container_id)
                except DockerAPIError as error:
                    if error.response.status_code != 404:
                        raise
                    else:
                        break

        log.info("Removing container %s:%s", container_name, container_id)
        for _ in until(timeout=10, action="removing container\tcontainer_name={0}\tcontainer_id={1}".format(container_name, container_id)):
            try:
                self.docker_context.remove_container(container_id)
                break
            except socket.timeout:
                break
            except ValueError:
                log.warning("Failed to remove container\tcontainer_id=%s", container_id)
            except DockerAPIError as error:
                if error.response.status_code != 404:
                    raise
                else:
                    break

    def build_image(self):
        """Build this image"""
        docker_lines = self.image_configuration.commands.docker_file()
        with self.image_configuration.context.make_context(self.parent_dir, docker_lines, self.mtime, silent_build=self.harpoon.silent_build, extra_context=self.image_configuration.commands.extra_context) as context:
            context_size = humanize.naturalsize(os.stat(context.name).st_size)
            log.info("Building '%s' in '%s' with %s of context", self.image_configuration.name, self.image_configuration.context.parent_dir, context_size)

            current_ids = None
            if not self.harpoon.keep_replaced:
                images = self.docker_context.images()
                current_ids = [image["Id"] for image in images if "{0}:latest".format(self.image_configuration.image_name) in image["RepoTags"]]

            buf = []
            cached = None
            last_line = ""
            current_hash = None
            try:
                for line in self.docker_context.build(fileobj=context, custom_context=True, tag=self.image_configuration.image_name, stream=True, rm=True):
                    line_detail = None
                    try: line_detail = json.loads(line)
                    except (ValueError, TypeError) as error:
                        log.warning("line from docker wasn't json", got=line, error=error)

                    if line_detail:
                        if "errorDetail" in line_detail:
                            raise FailedImage("Failed to build an image", image=self.name, msg=line_detail["errorDetail"].get("message", line_detail["errorDetail"]))

                        if "stream" in line_detail:
                            line = line_detail["stream"]
                        elif "status" in line_detail:
                            line = line_detail["status"]
                            if line.startswith("Pulling image"):
                                if not line.endswith("\n"):
                                    line = "{0}\n".format(line)
                            else:
                                line = "\r{0}".format(line)

                        if last_line.strip() == "---> Using cache":
                            current_hash = line.split(" ", 1)[0].strip()
                        elif line.strip().startswith("---> Running in"):
                            current_hash = line[len("---> Running in "):].strip()

                    if line.strip().startswith("---> Running in"):
                        cached = False
                        buf.append(line)
                    elif line.strip().startswith("---> Using cache"):
                        cached = True

                    last_line = line
                    if cached is None:
                        if "already being pulled by another client" in line or "Pulling repository" in line:
                            cached = False
                        else:
                            buf.append(line)
                            continue

                    if not self.harpoon.silent_build or not cached:
                        if buf:
                            for thing in buf:
                                sys.stdout.write(thing.encode('utf-8', 'replace'))
                                sys.stdout.flush()
                            buf = []

                        sys.stdout.write(line.encode('utf-8', 'replace'))
                        sys.stdout.flush()

                if current_ids:
                    images = self.docker_context.images()
                    untagged = [image["Id"] for image in images if image["RepoTags"] == ["<none>:<none>"]]
                    for image in current_ids:
                        if image in untagged:
                            log.info("Deleting replaced image\ttag=%s\told_hash=%s", "{0}:latest".format(self.image_configuration.image_name), image)
                            try:
                                self.docker_context.remove_image(image)
                            except Exception as error:
                                log.error("Failed to remove replaced image\thash=%s\terror=%s", image, error)
            except (KeyboardInterrupt, Exception) as error:
                exc_info = sys.exc_info()
                if current_hash:
                    with self.intervention(current_hash):
                        log.info("Removing bad container\thash=%s", current_hash)

                        try:
                            self.docker_context.kill(current_hash, signal=9)
                        except Exception as error:
                            log.error("Failed to kill dead container\thash=%s\terror=%s", current_hash, error)
                        try:
                            self.docker_context.remove_container(current_hash)
                        except Exception as error:
                            log.error("Failed to remove dead container\thash=%s\terror=%s", current_hash, error)

                if isinstance(error, KeyboardInterrupt):
                    raise UserQuit()
                else:
                    raise exc_info[1], None, exc_info[2]

    @contextmanager
    def intervention(self, container_id):
        """Ask the user if they want to commit this container and run /bin/bash in it"""
        if not self.harpoon.interactive or self.harpoon.no_intervention:
            yield
            return

        print("!!!!")
        print("It would appear building the image failed")
        print("Do you want to run /bin/bash where the build to help debug why it failed?")
        answer = raw_input("[y]: ")
        if answer and not answer.lower().startswith("y"):
            yield
            return

        with self.commit_and_run(container_id, command="/bin/bash"):
            yield

    @contextmanager
    def commit_and_run(self, container_id, command="/bin/bash"):
        """Commit this container id and run the provided command in it and clean up afterwards"""
        image_hash = None
        try:
            image = self.docker_context.commit(container_id)
            image_hash = image["Id"]

            name = "{0}-intervention-{1}".format(container_id, str(uuid.uuid1()))
            self._run_container(name, image_hash, image_hash, detach=False, tty=True, command=command, delete_on_exit=True, no_intervention=True)
            yield
        except Exception as error:
            log.error("Something failed about creating the intervention image\terror=%s", error)
            raise
        finally:
            try:
                if image_hash:
                    self.docker_context.remove_image(image_hash)
            except Exception as error:
                log.error("Failed to kill intervened image\thash=%s\terror=%s", image_hash, error)

class Imager(object):
    """Knows how to build and run docker images"""
    def __init__(self, configuration, docker_context):
        self.configuration = configuration
        self.docker_context = docker_context

    @property
    def images(self):
        """Make our image objects"""
        if not getattr(self, "_images", None):
            images = {}

            options = {"docker_context": self.docker_context}
            for key in self.configuration["images"].keys():
                images[key] = Image(key, self.configuration, ["images", key], **options)

            self._images = images
        return self._images

    def run(self, image, configuration):
        """Make this image and run it"""
        self.make_image(image)

        try:
            self.images[image].run_container(self.images)
        except DockerAPIError as error:
            raise BadImage("Failed to start the container", error=error)

    def make_image(self, image, chain=None, made=None, ignore_deps=False):
        """Make us an image"""
        if chain is None:
            chain = []

        if made is None:
            made = {}

        if image in made:
            return

        if image in chain:
            raise BadCommand("Recursive FROM statements", chain=chain + [image])

        images = self.images
        if image not in images:
            raise NoSuchImage(looking_for=image, available=images.keys())

        if not ignore_deps:
            for dependency, _ in images[image].image_configuration.dependency_images(images):
                self.make_image(dependency, chain=chain + [image], made=made)

        # Should have all our dependencies now
        instance = images[image]
        log.info("Making image for '%s' (%s) - FROM %s", instance.image_configuration.name, instance.image_configuration.image_name, instance.image_configuration.commands.parent_image_name)
        instance.build_image()
        made[image] = True

    def layered(self, only_pushable=False):
        """Yield layers of images"""
        images = self.images
        if only_pushable:
            operate_on = dict((image, instance) for image, instance in images.items() if instance.image_configuration.image_index)
        else:
            operate_on = images

        layers = Layers(operate_on, all_images=images)
        layers.add_all_to_layers()
        return layers.layered

