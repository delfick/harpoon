"""
The runner knows about starting a container from a docker image.

It is responsible for also starting any dependency containers that are included
via ``volumes.share_with`` or ``link``.

It will also ensure containers are killed and removed after use.

Finally, the Runner is also responsible for starting and cleaning up intervention
containers.
"""

from harpoon.errors import BadOption, BadImage, BadResult, UserQuit, AlreadyBoundPorts
from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon import helpers as hp
from harpoon.helpers import until

from docker.errors import APIError as DockerAPIError
from input_algorithms.spec_base import NotSpecified
from input_algorithms.meta import Meta
from contextlib import contextmanager
from harpoon import dockerpty
from six.moves import input
import docker.errors
import logging
import socket
import uuid
import time
import six
import os

log = logging.getLogger("harpoon.ship.runner")

class Runner(object):
    """Knows how to run containers given Image objects"""

    ########################
    ###   USAGE
    ########################

    def run_container(self, conf, images, **kwargs):
        """Run this image and all dependency images"""
        with self._run_container(conf, images, **kwargs):
            pass

    @contextmanager
    def _run_container(self, conf, images, detach=False, started=None, dependency=False, tag=None, delete_anyway=False):
        if conf.container_id:
            yield
            return

        try:
            self.run_deps(conf, images)
            tty = not detach and (dependency or conf.harpoon.interactive)
            container_id = self.create_container(conf, detach, tty)

            conf.container_id = container_id

            try:
                self.wait_for_deps(conf, images)
            except KeyboardInterrupt:
                raise UserQuit()

            self.start_container(conf, tty=tty, detach=detach, is_dependency=dependency)
            yield
        finally:
            if delete_anyway or (not detach and not dependency):
                self.stop_deps(conf, images)
                self.stop_container(conf, tag=tag)
                self.delete_deps(conf, images)

    ########################
    ###   DEPS
    ########################

    def delete_deps(self, conf, images):
        """Delete any deleteable images"""
        for dependency_name, _ in conf.dependency_images():
            image = images[dependency_name]
            if image.deleteable_image:
                log.info("Removing un-needed image {0}".format(image.image_name))
                conf.harpoon.docker_api.remove_image(image.image_name)

    def run_deps(self, conf, images):
        """Start containers for all our dependencies"""
        for dependency_name, detached in conf.dependency_images(for_running=True):
            try:
                self.run_container(images[dependency_name], images, detach=detached, dependency=True)
            except Exception as error:
                raise BadImage("Failed to start dependency container", image=conf.name, dependency=dependency_name, error=error)

    def stop_deps(self, conf, images):
        """Stop the containers for all our dependencies"""
        for dependency, _ in conf.dependency_images():
            self.stop_deps(images[dependency], images)
            try:
                self.stop_container(images[dependency], fail_on_bad_exit=True, fail_reason="Failed to run dependency container")
            except BadImage:
                raise
            except Exception as error:
                log.warning("Failed to stop dependency container\timage=%s\tdependency=%s\tcontainer_name=%s\terror=%s", conf.name, dependency, images[dependency].container_name, error)

    def wait_for_deps(self, conf, images):
        """Wait for all our dependencies"""
        from harpoon.option_spec.image_objs import WaitCondition
        api = conf.harpoon.docker_context_maker().api

        waited = set()
        last_attempt = {}
        dependencies = set(dep for dep, _ in conf.dependency_images())

        # Wait conditions come from dependency_options first
        # Or if none specified there, they come from the image itself
        wait_conditions = {}
        for dependency in dependencies:
            if conf.dependency_options is not NotSpecified and dependency in conf.dependency_options and conf.dependency_options[dependency].wait_condition is not NotSpecified:
                wait_conditions[dependency] = conf.dependency_options[dependency].wait_condition
            elif images[dependency].wait_condition is not NotSpecified:
                wait_conditions[dependency] = images[dependency].wait_condition

        if not wait_conditions:
            return

        start = time.time()
        while True:
            this_round = []
            for dependency in dependencies:
                if dependency in waited:
                    continue

                image = images[dependency]
                if dependency in wait_conditions:
                    done = self.wait_for_dep(api, image, wait_conditions[dependency], start, last_attempt.get(dependency))
                    this_round.append(done)
                    if done is True:
                        waited.add(dependency)
                    elif done is False:
                        last_attempt[dependency] = time.time()
                    elif done is WaitCondition.Timedout:
                        log.warning("Stopping dependency because it timedout waiting\tcontainer_id=%s", image.container_id)
                        self.stop_container(image)
                else:
                    waited.add(dependency)

            if set(this_round) != set([WaitCondition.KeepWaiting]):
                if dependencies - waited == set():
                    log.info("Finished waiting for dependencies")
                    break
                else:
                    log.info("Still waiting for dependencies\twaiting_on=%s", list(dependencies-waited))

                couldnt_wait = set()
                container_ids = {}
                for dependency in dependencies:
                    if dependency in waited:
                        continue

                    image = images[dependency]
                    if image.container_id is None:
                        stopped = True
                        if dependency not in container_ids:
                            available = sorted([i for i in available if "/{0}".format(image.container_name) in i["Names"]], key=lambda i: i["Created"])
                            if available:
                                container_ids[dependency] = available[0]["Id"]
                    else:
                        if dependency not in container_ids:
                            container_ids[dependency] = image.container_id
                        stopped, _ = self.is_stopped(image, image.container_id)

                    if stopped:
                        couldnt_wait.add(dependency)

                if couldnt_wait:
                    for container in couldnt_wait:
                        if container not in images or container not in container_ids:
                            continue
                        image = images[container]
                        container_id = container_ids[container]
                        container_name = image.container_name
                        hp.write_to(conf.harpoon.stdout, "=================== Logs for failed container {0} ({1})\n".format(container_id, container_name))
                        for line in conf.harpoon.docker_api.logs(container_id).split("\n"):
                            hp.write_to(conf.harpoon.stdout, "{0}\n".format(line))
                        hp.write_to(conf.harpoon.stdout, "------------------- End logs for failed container\n")
                    raise BadImage("One or more of the dependencies stopped running whilst waiting for other dependencies", stopped=list(couldnt_wait))

            time.sleep(0.1)

    def wait_for_dep(self, api, conf, wait_condition, start, last_attempt):
        """Wait for this image"""
        from harpoon.option_spec.image_objs import WaitCondition
        conditions = list(wait_condition.conditions(start, last_attempt))
        if conditions[0] in (WaitCondition.KeepWaiting, WaitCondition.Timedout):
            return conditions[0]

        log.info("Waiting for %s", conf.container_name)
        for condition in conditions:
            log.debug("Running condition\tcondition=%s", condition)
            command = 'bash -c "{0}"'.format(condition)
            try:
                exec_id = api.exec_create(conf.container_id, command, tty=False)
            except DockerAPIError as error:
                log.error("Failed to run condition\tcondition=%s\tdependency=%s\terror=%s", condition, conf.name, error)
                return False

            output = api.exec_start(exec_id).decode('utf-8')
            inspection = api.exec_inspect(exec_id)
            exit_code = inspection["ExitCode"]
            if exit_code != 0:
                log.error("Condition says no\tcondition=%s\toutput:\n\t%s", condition, "\n\t".join(line for line in output.split('\n')))
                return False

        log.info("Finished waiting for %s", conf.container_name)
        return True

    ########################
    ###   CREATION
    ########################

    def exposed(self, ports):
        result = {}
        for p in ports:
            key = '/'.join(str(s) for s in p.container_port.port_pair)
            result[key] = {"HostIP": "0.0.0.0", "HostPort": "{0}/tcp".format(p.host_port)}
        return result

    def create_container(self, conf, detach, tty):
        """Create a single container"""

        name = conf.name
        image_name = conf.image_name
        if conf.tag is not NotSpecified:
            image_name = conf.image_name_with_tag
        container_name = conf.container_name

        with conf.assumed_role():
            env = dict(e.pair for e in conf.env)

        binds = conf.volumes.binds
        command = conf.formatted_command
        volume_names = conf.volumes.volume_names
        volumes_from = list(conf.volumes.share_with_names)
        no_tty_option = conf.no_tty_option

        ports = [p.container_port.port_pair for p in conf.ports]
        port_bindings = self.exposed(conf.ports)

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
        if port_bindings:
            log.info("\tPort bindings: %s", port_bindings)
        if volumes_from:
            log.info("\tVolumes from: %s", volumes_from)

        host_config = conf.harpoon.docker_api.create_host_config(
              binds = binds
            , volumes_from = volumes_from
            , port_bindings = port_bindings

            , devices = conf.devices
            , lxc_conf = conf.lxc_conf
            , privileged = conf.privileged
            , restart_policy = conf.restart_policy

            , dns = conf.network.dns
            , dns_search = conf.network.dns_search
            , extra_hosts = conf.network.extra_hosts
            , network_mode = conf.network.network_mode
            , publish_all_ports = conf.network.publish_all_ports

            , cap_add = conf.cpu.cap_add
            , cap_drop = conf.cpu.cap_drop
            , mem_limit = conf.cpu.mem_limit
            , cpu_shares = conf.cpu.cpu_shares
            , cpuset_cpus = conf.cpu.cpuset_cpus
            , cpuset_mems = conf.cpu.cpuset_mems
            , memswap_limit = conf.cpu.memswap_limit

            , ulimits = conf.ulimits
            , read_only = conf.read_only_rootfs
            , log_config = conf.log_config
            , security_opt = conf.security_opt

            , **conf.other_options.host_config
            )

        container_id = conf.harpoon.docker_api.create_container(image_name
            , name=container_name
            , detach=detach
            , command=command
            , volumes=volume_names
            , environment=env

            , tty = False if no_tty_option else tty
            , user = conf.user
            , ports = ports
            , stdin_open = tty

            , hostname = conf.network.hostname
            , domainname = conf.network.domainname
            , network_disabled = conf.network.disabled

            , host_config = host_config

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
        # Make sure we can bind to our specified ports!
        if not conf.harpoon.docker_api.base_url.startswith("http"):
            self.find_bound_ports(conf.ports)

        container_id = conf.container_id
        container_name = conf.container_name

        conf.harpoon.network_manager.register(conf, container_name)

        log.info("Starting container %s (%s)", container_name, container_id)

        try:
            if not detach and not is_dependency:
                self.start_tty(conf, interactive=tty, **conf.other_options.start)
            else:
                conf.harpoon.docker_api.start(container_id
                    , **conf.other_options.start
                    )
        except docker.errors.APIError as error:
            if str(error).startswith("404 Client Error: Not Found"):
                log.error("Container died before we could even get to it...")

        inspection = None
        if not detach and not is_dependency:
            inspection = self.get_exit_code(conf)

        if inspection and not no_intervention:
            if not inspection["State"]["Running"] and inspection["State"]["ExitCode"] != 0:
                self.stage_run_intervention(conf)
                raise BadImage("Failed to run container", container_id=container_id, container_name=container_name, reason="nonzero exit code after launch")

        if not is_dependency and conf.harpoon.intervene_afterwards and not no_intervention:
            self.stage_run_intervention(conf, just_do_it=True)

    def start_tty(self, conf, interactive):
        """Startup a tty"""
        try:
            api = conf.harpoon.docker_context_maker().api
            container_id = conf.container_id

            stdin = conf.harpoon.tty_stdin
            stdout = conf.harpoon.tty_stdout
            stderr = conf.harpoon.tty_stderr
            if callable(stdin): stdin = stdin()
            if callable(stdout): stdout = stdout()
            if callable(stderr): stderr = stderr()
            dockerpty.start(api, container_id, interactive=interactive, stdout=stdout, stderr=stderr, stdin=stdin)
        except KeyboardInterrupt:
            pass

    ########################
    ###   STOPPING
    ########################

    def wait_till_stopped(self, conf, container_id, timeout=10, message=None, waiting=True):
        """Wait till a container is stopped"""
        stopped = False
        inspection = None
        for _ in until(timeout=timeout, action=message):
            try:
                inspection = conf.harpoon.docker_api.inspect_container(container_id)
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

        if not inspection:
            log.warning("Failed to inspect the container!")
            stopped = True
            exit_code = 1
        else:
            exit_code = inspection["State"]["ExitCode"]
        return stopped, exit_code

    def is_stopped(self, *args, **kwargs):
        """Return whether this container is stopped"""
        kwargs["waiting"] = False
        return self.wait_till_stopped(*args, **kwargs)

    def stop_container(self, conf, fail_on_bad_exit=False, fail_reason=None, tag=None, remove_volumes=False):
        """Stop some container"""
        stopped = False
        container_id = conf.container_id
        if not container_id:
            return

        container_name = conf.container_name
        stopped, exit_code = self.is_stopped(conf, container_id)

        if stopped:
            if exit_code != 0 and fail_on_bad_exit:
                if not conf.harpoon.interactive:
                    print_logs = True
                else:
                    hp.write_to(conf.harpoon.stdout, "!!!!\n")
                    hp.write_to(conf.harpoon.stdout, "Container had already exited with a non zero exit code\tcontainer_name={0}\tcontainer_id={1}\texit_code={2}\n".format(container_name, container_id, exit_code))
                    hp.write_to(conf.harpoon.stdout, "Do you want to see the logs from this container?\n")
                    conf.harpoon.stdout.flush()
                    answer = input("[y]: ")
                    print_logs = not answer or answer.lower().startswith("y")

                if print_logs:
                    hp.write_to(conf.harpoon.stdout, "=================== Logs for failed container {0} ({1})\n".format(container_id, container_name))
                    logs = conf.harpoon.docker_api.logs(container_id)
                    if isinstance(logs, six.binary_type):
                        logs = logs.decode()
                    for line in logs.split("\n"):
                        hp.write_to(conf.harpoon.stdout, "{0}\n".format(line))
                    hp.write_to(conf.harpoon.stdout, "------------------- End logs for failed container\n")
                fail_reason = fail_reason or "Failed to run container"
                raise BadImage(fail_reason, container_id=container_id, container_name=container_name)
        else:
            try:
                log.info("Killing container %s:%s", container_name, container_id)
                conf.harpoon.docker_api.kill(container_id, 9)
            except DockerAPIError:
                pass
            self.wait_till_stopped(conf, container_id, timeout=10, message="waiting for container to die\tcontainer_name={0}\tcontainer_id={1}".format(container_name, container_id))

        if tag:
            log.info("Tagging a container\tcontainer_id=%s\ttag=%s", container_id, tag)
            new_id = conf.harpoon.docker_api.commit(container_id)["Id"]
            conf["committed"] = new_id
            if tag is not True:
                the_tag = "latest" if conf.tag is NotSpecified else conf.tag
                conf.harpoon.docker_api.tag(new_id, repository=tag, tag=the_tag, force=True)

        mounts = []
        if remove_volumes:
            inspection = conf.harpoon.docker_api.inspect_container(container_id)
            if "Mounts" in inspection:
                for m in inspection["Mounts"]:
                    if "Name" in m:
                        mounts.append(m['Name'])
            else:
                log.warning("Your docker can't inspect and delete volumes :(")

        if not conf.harpoon.no_cleanup:
            log.info("Removing container %s:%s", container_name, container_id)
            for _ in until(timeout=10, action="removing container\tcontainer_name={0}\tcontainer_id={1}".format(container_name, container_id)):
                try:
                    conf.harpoon.docker_api.remove_container(container_id)
                    break
                except socket.timeout:
                    break
                except (ValueError, DockerAPIError) as error:
                    log.warning("Failed to remove container\tcontainer_id=%s\terror=%s", container_id, error)

        for mount in mounts:
            try:
                log.info("Cleaning up volume {0}".format(mount))
                conf.harpoon.docker_api.remove_volume(mount)
            except DockerAPIError as error:
                log.warning("Failed to cleanup volume\tvolume=%s\terror=%s", mount, error)

        conf.harpoon.network_manager.removed(container_name)

    ########################
    ###   UTILITY
    ########################

    def get_exit_code(self, conf):
        """Determine how a container exited"""
        for _ in until(timeout=0.5, step=0.1, silent=True):
            try:
                inspection = conf.harpoon.docker_api.inspect_container(conf.container_id)
                if not isinstance(inspection, dict) or "State" not in inspection:
                    raise BadResult("Expected inspect result to be a dictionary with 'State' in it", found=inspection)
                elif not inspection["State"]["Running"]:
                    return inspection
            except Exception as error:
                log.error("Failed to see if container exited normally or not\thash=%s\terror=%s", conf.container_id, error)

    def find_bound_ports(self, ports):
        """Find any ports that are already bound and complain about them"""
        bound = []
        for port in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind((port.ip if port.ip is not NotSpecified else "127.0.0.1", port.host_port))
            except socket.error as error:
                bound.append(port.host_port)
            finally:
                s.close()

        if bound:
            raise AlreadyBoundPorts(ports=bound)

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
            hp.write_to(conf.harpoon.stdout, "!!!!\n")
            hp.write_to(conf.harpoon.stdout, "Failed to run the container!\n")
            hp.write_to(conf.harpoon.stdout, "Do you want commit the container in it's current state and {0} into it to debug?\n".format(conf.resolved_shell))
            conf.harpoon.stdout.flush()
            answer = input("[y]: ")
        if not answer or answer.lower().startswith("y"):
            with self.commit_and_run(conf.container_id, conf, command=conf.resolved_shell):
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
                conf.harpoon.docker_api.kill(container, signal=9)
            except Exception as error:
                log.error("Failed to kill dead container\thash=%s\terror=%s", container, error)
            try:
                conf.harpoon.docker_api.remove_container(container)
            except Exception as error:
                log.error("Failed to remove dead container\thash=%s\terror=%s", container, error)

    @contextmanager
    def intervention(self, commit, conf):
        """Ask the user if they want to commit this container and run sh in it"""
        if not conf.harpoon.interactive or conf.harpoon.no_intervention:
            yield
            return

        hp.write_to(conf.harpoon.stdout, "!!!!\n")
        hp.write_to(conf.harpoon.stdout, "It would appear building the image failed\n")
        hp.write_to(conf.harpoon.stdout, "Do you want to run {0} where the build to help debug why it failed?\n".format(conf.resolved_shell))
        conf.harpoon.stdout.flush()
        answer = input("[y]: ")
        if answer and not answer.lower().startswith("y"):
            yield
            return

        with self.commit_and_run(commit, conf, command=conf.resolved_shell):
            yield

    @contextmanager
    def commit_and_run(self, commit, conf, command="sh"):
        """Commit this container id and run the provided command in it and clean up afterwards"""
        image_hash = None
        try:
            image_hash = conf.harpoon.docker_api.commit(commit)["Id"]

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
                    conf.harpoon.docker_api.remove_image(image_hash)
            except Exception as error:
                log.error("Failed to kill intervened image\thash=%s\terror=%s", image_hash, error)
