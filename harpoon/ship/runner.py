"""
The runner knows about starting a container from a docker image.

It is responsible for also starting any dependency containers that are included
via ``volumes.share_with`` or ``link``.

It will also ensure containers are killed and removed after use.

Finally, the Runner is also responsible for starting and cleaning up intervention
containers.
"""

from __future__ import print_function

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.errors import BadOption, BadImage, BadResult
from harpoon.helpers import until

from docker.errors import APIError as DockerAPIError
from input_algorithms.spec_base import NotSpecified
from input_algorithms.meta import Meta
from contextlib import contextmanager
from harpoon import dockerpty
import logging
import socket
import uuid
import os

log = logging.getLogger("harpoon.ship.runner")

class Runner(object):
    """Knows how to run containers given Image objects"""

    ########################
    ###   USAGE
    ########################

    def run_container(self, conf, images, detach=False, started=None, dependency=False, tag=None):
        """Run this image and all dependency images"""
        if conf.container_id:
            return

        try:
            self.run_deps(conf, images)
            tty = not detach and (dependency or conf.harpoon.interactive)
            container_id = self.create_container(conf, detach, tty)

            conf.container_id = container_id
            self.start_container(conf, tty=tty, detach=detach, is_dependency=dependency)
        finally:
            if not detach and not dependency:
                self.stop_deps(conf, images)
                self.stop_container(conf, tag=tag)

    ########################
    ###   DEPS
    ########################

    def run_deps(self, conf, images):
        """Start containers for all our dependencies"""
        for dependency_name, detached in conf.dependency_images():
            try:
                self.run_container(images[dependency_name], images, detach=detached, dependency=True)
            except Exception as error:
                raise BadImage("Failed to start dependency container", image=conf.name, dependency=dependency_name, error=error)

    def stop_deps(self, conf, images):
        """Stop the containers for all our dependencies"""
        for dependency, _ in conf.dependency_images():
            try:
                self.stop_container(images[dependency], fail_on_bad_exit=True, fail_reason="Failed to run dependency container")
            except BadImage:
                raise
            except Exception as error:
                log.warning("Failed to stop dependency container\timage=%s\tdependency=%s\tcontainer_name=%s\terror=%s", conf.name, dependency, images[dependency].container_name, error)

    ########################
    ###   CREATION
    ########################

    def create_container(self, conf, detach, tty):
        """Create a single container"""

        name = conf.name
        image_name = conf.image_name
        container_name = conf.container_name

        env = dict(e.pair for e in conf.env)
        ports = [port.host_port for port in conf.ports]
        binds = conf.volumes.binds
        command = conf.formatted_command
        volume_names = conf.volumes.volume_names

        uncreated = []
        for name in binds:
            if not os.path.exists(name):
                log.info("Making volume for mounting\tvolume=%s", name)
                try:
                    os.makedirs(name)
                except OSError as error:
                    uncreated.append((name, error))
        if uncreated:
            raise BadOption("Failed to create some volumes on the host", uncreated=uncreated)

        log.info("Creating container from %s\timage=%s\tcontainer_name=%s\ttty=%s", image_name, name, container_name, tty)
        if binds:
            log.info("\tUsing volumes\tvolumes=%s", volume_names)
        if env:
            log.info("\tUsing environment\tenv=%s", sorted(env.keys()))
        if ports:
            log.info("\tUsing ports\tports=%s", ports)

        container_id = conf.harpoon.docker_context.create_container(image_name
            , name=container_name
            , detach=detach
            , command=command
            , volumes=volume_names
            , environment=env

            , tty = tty
            , user = conf.user
            , ports = ports
            , stdin_open = tty

            , dns = conf.network.dns
            , hostname = conf.network.hostname
            , domainname = conf.network.domainname
            , network_disabled = conf.network.disabled

            , cpuset = conf.cpu.cpuset
            , mem_limit = conf.cpu.mem_limit
            , cpu_shares = conf.cpu.cpu_shares
            , memswap_limit = conf.cpu.memswap_limit

            , **conf.other_options.create
            )

        if isinstance(container_id, dict):
            if "errorDetail" in container_id:
                raise BadImage("Failed to create container", image=name, error=container_id["errorDetail"])
            container_id = container_id["Id"]

        return container_id

    ########################
    ###   RUNNING
    ########################

    def start_container(self, conf, tty=True, detach=False, is_dependency=False, no_intervention=False):
        """Start up a single container"""
        binds = conf.volumes.binds
        links = [link.pair for link in conf.links]
        ports = dict([port.pair for port in conf.ports])
        volumes_from = list(conf.volumes.share_with_names)
        container_id = conf.container_id
        container_name = conf.container_name

        log.info("Starting container %s (%s)", container_name, container_id)
        if links:
            log.info("\tLinks: %s", links)
        if volumes_from:
            log.info("\tVolumes from: %s", volumes_from)
        if ports:
            log.info("\tPort bindings: %s", ports)

        conf.harpoon.docker_context.start(container_id
            , links = links
            , binds = binds
            , port_bindings = ports
            , volumes_from = volumes_from

            , devices = conf.devices
            , lxc_conf = conf.lxc_conf
            , privileged = conf.privileged
            , restart_policy = conf.restart_policy

            , dns = conf.network.dns
            , dns_search = conf.network.dns_search
            , extra_hosts = conf.network.extra_hosts
            , network_mode = conf.network.mode
            , publish_all_ports = conf.network.publish_all_ports

            , cap_add = conf.cpu.cap_add
            , cap_drop = conf.cpu.cap_drop

            , **conf.other_options.run
            )

        if not detach and not is_dependency:
            self.start_tty(conf, interactive=tty)

        inspection = None
        if not detach and not is_dependency:
            inspection = self.get_exit_code(conf)

        if inspection and not no_intervention:
            if not inspection["State"]["Running"] and inspection["State"]["ExitCode"] != 0:
                self.stage_run_intervention(conf)
                raise BadImage("Failed to run container", container_id=container_id, container_name=container_name)

        if not is_dependency and conf.harpoon.intervene_afterwards and not no_intervention:
            self.stage_run_intervention(conf, just_do_it=True)

    def start_tty(self, conf, interactive):
        """Startup a tty"""
        try:
            ctxt = conf.harpoon.docker_context_maker()
            container_id = conf.container_id
            dockerpty.start(ctxt, container_id, interactive=interactive)
        except KeyboardInterrupt:
            pass

    ########################
    ###   STOPPING
    ########################

    def stop_container(self, conf, fail_on_bad_exit=False, fail_reason=None, tag=None):
        """Stop some container"""
        stopped = False
        container_id = conf.container_id
        if not container_id:
            return

        container_name = conf.container_name
        for _ in until(timeout=10):
            try:
                inspection = conf.harpoon.docker_context.inspect_container(container_id)
                if not isinstance(inspection, dict):
                    log.error("Weird response from inspecting the container\tresponse=%s", inspection)
                else:
                    if not inspection["State"]["Running"]:
                        stopped = True
                        conf.container_id = None
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
                if not conf.harpoon.interactive:
                    print_logs = True
                else:
                    print("!!!!")
                    print("Container had already exited with a non zero exit code\tcontainer_name={0}\tcontainer_id={1}\texit_code={2}".format(container_name, container_id, exit_code))
                    print("Do you want to see the logs from this container?")
                    answer = raw_input("[y]: ")
                    print_logs = not answer or answer.lower().startswith("y")

                if print_logs:
                    print("=================== Logs for failed container {0} ({1})".format(container_id, container_name))
                    for line in conf.harpoon.docker_context.logs(container_id).split("\n"):
                        print(line)
                    print("------------------- End logs for failed container")
                fail_reason = fail_reason or "Failed to run container"
                raise BadImage(fail_reason, container_id=container_id, container_name=container_name)
        else:
            try:
                log.info("Killing container %s:%s", container_name, container_id)
                conf.harpoon.docker_context.kill(container_id, 9)
            except DockerAPIError:
                pass

            for _ in until(timeout=10, action="waiting for container to die\tcontainer_name={0}\tcontainer_id={1}".format(container_name, container_id)):
                try:
                    inspection = conf.harpoon.docker_context.inspect_container(container_id)
                    if not inspection["State"]["Running"]:
                        conf.container_id = None
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

        if tag:
            log.info("Tagging a container\tcontainer_id=%s\ttag=%s", container_id, tag)
            new_id = conf.harpoon.docker_context.commit(container_id)["Id"]
            conf.harpoon.docker_context.tag(new_id, repository=tag, tag="latest", force=True)

        if not conf.harpoon.no_cleanup:
            log.info("Removing container %s:%s", container_name, container_id)
            for _ in until(timeout=10, action="removing container\tcontainer_name={0}\tcontainer_id={1}".format(container_name, container_id)):
                try:
                    conf.harpoon.docker_context.remove_container(container_id)
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

    ########################
    ###   UTILITY
    ########################

    def get_exit_code(self, conf):
        """Determine how a container exited"""
        for _ in until(timeout=0.5, step=0.1, silent=True):
            try:
                inspection = conf.harpoon.docker_context.inspect_container(conf.container_id)
                if not isinstance(inspection, dict) or "State" not in inspection:
                    raise BadResult("Expected inspect result to be a dictionary with 'State' in it", found=inspection)
                elif not inspection["State"]["Running"]:
                    return inspection
            except Exception as error:
                log.error("Failed to see if container exited normally or not\thash=%s\terror=%s", conf.container_id, error)

    ########################
    ###   INTERVENTION
    ########################

    def stage_run_intervention(self, conf, just_do_it=False):
        """Start an intervention!"""
        if not conf.harpoon.interactive or conf.harpoon.no_intervention:
            return

        if just_do_it:
            answer = 'y'
        else:
            print("!!!!")
            print("Failed to run the container!")
            print("Do you want commit the container in it's current state and /bin/bash into it to debug?")
            answer = raw_input("[y]: ")
        if not answer or answer.lower().startswith("y"):
            with self.commit_and_run(conf.container_id, conf, command="/bin/bash"):
                pass

    def stage_build_intervention(self, conf, container):
        if not container:
            return

        conf = conf.configuration.root().wrapped()
        conf.update({"_key_name_1": "{0}_intervention".format(container), "commands": []})
        conf = HarpoonSpec().image_spec.normalise(Meta(conf, []), conf)

        with self.intervention(container, conf):
            log.info("Removing bad container\thash=%s", container)

            try:
                conf.harpoon.docker_context.kill(container, signal=9)
            except Exception as error:
                log.error("Failed to kill dead container\thash=%s\terror=%s", container, error)
            try:
                conf.harpoon.docker_context.remove_container(container)
            except Exception as error:
                log.error("Failed to remove dead container\thash=%s\terror=%s", container, error)

    @contextmanager
    def intervention(self, commit, conf):
        """Ask the user if they want to commit this container and run /bin/bash in it"""
        if not conf.harpoon.interactive or conf.harpoon.no_intervention:
            yield
            return

        print("!!!!")
        print("It would appear building the image failed")
        print("Do you want to run /bin/bash where the build to help debug why it failed?")
        answer = raw_input("[y]: ")
        if answer and not answer.lower().startswith("y"):
            yield
            return

        with self.commit_and_run(commit, conf, command="/bin/bash"):
            yield

    @contextmanager
    def commit_and_run(self, commit, conf, command="/bin/bash"):
        """Commit this container id and run the provided command in it and clean up afterwards"""
        image_hash = None
        try:
            image_hash = conf.harpoon.docker_context.commit(commit)["Id"]

            new_conf = conf.clone()
            new_conf.bash = NotSpecified
            new_conf.command = command
            new_conf.image_name = image_hash
            new_conf.container_id = None
            new_conf.container_name = "{0}-intervention-{1}".format(conf.container_id, str(uuid.uuid1()))

            container_id = self.create_container(new_conf, False, True)
            new_conf.container_id = container_id

            try:
                self.start_container(new_conf, tty=True, detach=False, is_dependency=False, no_intervention=True)
            finally:
                self.stop_container(new_conf)
            yield
        except Exception as error:
            log.error("Something failed about creating the intervention image\terror=%s", error)
            raise
        finally:
            try:
                if image_hash:
                    log.info("Removing intervened image\thash=%s", image_hash)
                    conf.harpoon.docker_context.remove_image(image_hash)
            except Exception as error:
                log.error("Failed to kill intervened image\thash=%s\terror=%s", image_hash, error)

