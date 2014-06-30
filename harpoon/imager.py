from harpoon.errors import NoSuchKey, BadOption, NoSuchImage, BadCommand, BadImage, ProgrammerError, HarpoonError, FailedImage, BadResult
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.helpers import a_temp_file, until
from harpoon.processes import command_output

from docker.errors import APIError as DockerAPIError
from option_merge import MergedOptions
from contextlib import contextmanager
import dockerpty
import humanize
import fnmatch
import tarfile
import logging
import socket
import json
import uuid
import sys
import os

log = logging.getLogger("harpoon.imager")

class NotSpecified(object):
    """Tell the difference between not specified and None"""

class Image(object):
    def __init__(self, name, all_configuration, path, docker_context, interactive=False, silent_build=False):
        self.name = name
        self.path = path
        self.interactive = interactive
        self.silent_build = silent_build
        self.docker_context = docker_context
        self.all_configuration = all_configuration

        self.already_running = False
        self.configuration = all_configuration[self.path]

    @property
    def image_name(self):
        return self.configuration["image_name"]

    @property
    def container_name(self):
        return self.configuration["container_name"]

    @property
    def mtime(self):
        val = self.heira_formatted("__mtime__", default=None)
        if val is not None:
            return int(val)

    @property
    def parent_image(self):
        """Look at the FROM statement to see what our parent image is"""
        if not hasattr(self, "commands"):
            raise ProgrammerError("Image.setup hasn't been called yet.")

        if not self.commands:
            raise BadImage("Image has no commands.....")

        first_command = self.commands[0]
        if not first_command.startswith("FROM"):
            raise BadImage("The first command isn't a FROM statement!", found=first_command, image=self.name)

        return first_command.split(" ", 1)[1]

    def dependency_images(self, images, ignore_parent=False):
        """
        What images does this one require

        Taking into account parent image, and those in link and volumes_from options
        """
        if not ignore_parent:
            for image, instance in images.items():
                if self.parent_image == instance.image_name:
                    yield image
                    break

        container_names = dict((instance.container_name, image) for image, instance in images.items())

        if self.link:
            for image in self.link:
                if ":" in image:
                    image = image.split(":", 1)[0]
                if image in container_names:
                    yield container_names[image]

        if self.volumes_from:
            for image in self.volumes_from:
                if image in container_names:
                    yield container_names[image]

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
            if any(name in container.get("Names", []) for name in (self.container_name, "/{0}".format(self.container_name))):
                self._container_id = container["Id"]
                break

        return self._container_id

    def push(self):
        """Push this image"""
        if not self.heira_formatted("image_index", default=None):
            raise BadImage("Can't push without an image_index configuration", image=self.name)
        for line in self.docker_context.push(self.image_name, stream=True):
            line_detail = None
            try:
                line_detail = json.loads(line)
            except (ValueError, TypeError) as error:
                log.warning("line from docker wasn't json", got=line, error=error)

            if line_detail:
                if "errorDetail" in line_detail:
                    raise FailedImage("Failed to push an image", image=self.name, image_name=self.image_name, msg=line_detail["errorDetail"].get("message", line_detail["errorDetail"]))
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

    def figure_out_env(self, extra_env):
        """Figure out combination of env from configuration and extra env"""
        env = self.heira_formatted("harpoon.env", default=None) or []
        if isinstance(env, dict):
            env = sorted("{0}={1}".format(key, val) for key, val in extra_env.items())

        if isinstance(extra_env, dict):
            env.extend(sorted("{0}={1}".format(key, val) for key, val in extra_env.items()))
        elif extra_env:
            env.extend(extra_env)

        result = []
        for thing in env:
            if '=' in env:
                result.append(thing)
            else:
                result.append("{0}={1}".format(thing, os.environ[thing]))
        return result

    def figure_out_ports(self, extra_ports):
        """Figure out the combination of ports, return as a dictionary"""
        result = {}
        harpoon_ports = self.heira_formatted("harpoon.ports", default=None)
        formatted_ports = self.heira_formatted("ports", default=None)
        for ports in (harpoon_ports, formatted_ports, extra_ports):
            if ports:
                if isinstance(ports, dict):
                    result.update(ports)
                    continue

                if not isinstance(ports, list):
                    ports = [ports]

                if isinstance(ports, list):
                    for port in ports:
                        if isinstance(port, basestring) and ":" in port:
                            key, val = port.split(":", 1)
                            result[key] = val
                        else:
                            result[port] = port
        return result

    def run_container(self, images, detach=False, command=None, started=None, extra_env=None, extra_volumes=None, extra_ports=None):
        """Run this image and all dependency images"""
        if self.already_running:
            return

        try:
            for dependency in self.dependency_images(images, ignore_parent=True):
                try:
                    images[dependency].run_container(images, detach=True)
                except Exception as error:
                    raise BadImage("Failed to start dependency container", image=self.name, dependency=dependency, error=error)

            env = self.figure_out_env(extra_env)
            ports = self.figure_out_ports(extra_ports)

            tty = not detach and self.interactive
            links = [link.split(":") for link in self.link]
            volumes = self.volumes
            if extra_volumes:
                if volumes is None:
                    volumes = []
                volumes.extend(extra_volumes)
            volumes_from = self.volumes_from
            self._run_container(self.name, self.image_name, self.container_name
                , detach=detach, command=command, tty=tty, env=env, ports=ports
                , volumes=volumes, volumes_from=volumes_from, links=links
                )

        finally:
            if not detach:
                for dependency in self.dependency_images(images, ignore_parent=True):
                    try:
                        images[dependency].stop_container()
                    except Exception as error:
                        log.warning("Failed to stop dependency container\timage=%s\tdependency=%s\tcontainer_name=%s\terror=%s", self.name, dependency, images[dependency].container_name, error)
                self.stop_container()

    def _run_container(self, name, image_name, container_name, detach=False, command=None, tty=True, volumes=None, volumes_from=None, links=None, delete_on_exit=False, env=None, ports=None):
        """Run a single container"""
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
                    bound, permissions = volume.split(":", 1)
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
            log.info("\tUsing environment\tenv=%s", env)
        if ports:
            log.info("\tUsing ports\tports=%s", ports.keys())
        container = self.docker_context.create_container(image_name
            , name=container_name
            , detach=detach
            , command=command
            , volumes=volumes
            , environment=env

            , tty = tty
            , ports = (ports or {}).keys()
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

            if not detach:
                dockerpty.start(self.docker_context, container_id)

            inspection = None
            if not detach:
                for _ in until(timeout=0.5, step=0.1, silent=True):
                    try:
                        inspection = self.docker_context.inspect_container(container_id)
                        if not isinstance(inspection, dict) or "State" not in inspection:
                            raise BadResult("Expected inspect result to be a dictionary with 'State' in it", found=inspection)
                        elif not inspection["State"]["Running"]:
                            break
                    except Exception as error:
                        log.error("Failed to see if container exited normally or not\thash=%s\terror=%s", container_id, error)

            if inspection:
                if not inspection["State"]["Running"] and inspection["State"]["ExitCode"] != 0:
                    raise BadImage("Failed to run container", container_id=container_id)
        finally:
            if delete_on_exit:
                self._stop_container(container_id, container_name)

    def stop_container(self):
        """Stop this container if it exists"""
        container_id = self.container_id
        if container_id is None:
            return

        self._stop_container(container_id, self.container_name)
        self._container_id = None
        self.already_running = False

    def _stop_container(self, container_id, container_name):
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

        if not stopped:
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
        with self.make_context() as context:
            context_size = humanize.naturalsize(os.stat(context.name).st_size)
            log.info("Building '%s' in '%s' with %s of context", self.name, self.parent_dir, context_size)

            current_ids = None
            if not self.heira_formatted("harpoon.keep_replaced", default=False):
                images = self.docker_context.images()
                current_ids = [image["Id"] for image in images if "{0}:latest".format(self.image_name) in image["RepoTags"]]

            buf = []
            cached = None
            last_line = ""
            current_hash = None
            try:
                for line in self.docker_context.build(fileobj=context, custom_context=True, tag=self.image_name, stream=True, rm=True):
                    line_detail = None
                    try:
                        line_detail = json.loads(line)
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

                        last_line = line_detail
                    else:
                        line = line
                    last_line = line

                    if line.strip().startswith("---> Running in"):
                        cached = False
                        buf.append(line)
                    elif line.strip().startswith("---> Using cache"):
                        cached = True

                    if cached is None:
                        if "already being pulled by another client" in line or "Pulling repository" in line:
                            cached = False
                        else:
                            buf.append(line)
                            continue

                    if not self.silent_build or not cached:
                        if buf:
                            for thing in buf:
                                sys.stdout.write(thing)
                                sys.stdout.flush()
                            buf = []

                        sys.stdout.write(line)
                        sys.stdout.flush()

                if current_ids:
                    images = self.docker_context.images()
                    untagged = [image["Id"] for image in images if image["RepoTags"] == ["<none>:<none>"]]
                    for image in current_ids:
                        if image in untagged:
                            log.info("Deleting replaced image\ttag=%s\told_hash=%s", "{0}:latest".format(self.image_name), image)
                            try:
                                self.docker_context.remove_image(image)
                            except Exception as error:
                                log.error("Failed to remove replaced image\thash=%s\terror=%s", image, error)
            except:
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

                raise exc_info[1], None, exc_info[2]

    @contextmanager
    def make_context(self):
        """Context manager for creating the context of the image"""
        host_context = not self.heira_formatted("no_host_context", default=False)
        context_exclude = self.heira_formatted("context_exclude", default=None)
        respect_gitignore = self.heira_formatted("respect_gitignore", default=False)

        files = []
        if host_context:
            if respect_gitignore:
                if not self.silent_build: log.info("Determining context from git ls-files")
                options = ""
                if context_exclude:
                    for excluder in context_exclude:
                        options = "{0} --exclude={1}".format(options, excluder)

                # Unfortunately --exclude doesn't work on committed/staged files, only on untracked things :(
                output, status = command_output("git ls-files --exclude-standard", cwd=self.parent_dir)
                if status != 0:
                    raise HarpoonError("Failed to do a git ls-files", directory=self.parent_dir, output=output)

                others, status = command_output("git ls-files --exclude-standard --others {0}".format(options), cwd=self.parent_dir)
                if status != 0:
                    raise HarpoonError("Failed to do a git ls-files to get untracked files", directory=self.parent_dir, output=others)

                if not (output or others) or any(out and out[0].startswith("fatal: Not a git repository") for out in (output, others)):
                    raise HarpoonError("Told to respect gitignore, but git ls-files says no", directory=self.parent_dir, output=output, others=others)

                combined = set(output + others)
                if context_exclude:
                    if not self.silent_build: log.info("Filtering %s items\texcluding=%s", len(combined), context_exclude)
                    excluded = set()
                    for filename in combined:
                        for excluder in context_exclude:
                            if fnmatch.fnmatch(filename, excluder):
                                excluded.add(filename)
                                break
                    combined = combined - excluded
                files = sorted(os.path.join(self.parent_dir, filename) for filename in combined)
                if not self.silent_build: log.info("Adding %s things from %s to the context", len(files), self.parent_dir)
            else:
                if context_exclude:
                    raise NotImplementedError("Sorry, can't use context_exclude if we aren't using git ls-files (set respect_gitignore to True)")
                files = [self.parent_dir]

        mtime = self.mtime
        docker_lines = '\n'.join(self.commands)
        with a_temp_file() as tmpfile:
            t = tarfile.open(mode='w', fileobj=tmpfile)
            for thing in files:
                if os.path.exists(thing):
                    arcname = "./{0}".format(os.path.relpath(thing, self.parent_dir))
                    t.add(thing, arcname=arcname)

            for content, arcname in self.extra_context:
                with a_temp_file() as fle:
                    fle.write(content)
                    fle.seek(0)
                    if mtime:
                        os.utime(fle.name, (mtime, mtime))
                    t.add(fle.name, arcname=arcname)

            # And add our docker file
            with a_temp_file() as dockerfile:
                dockerfile.write(docker_lines)
                dockerfile.seek(0)
                if mtime:
                    os.utime(dockerfile.name, (mtime, mtime))
                t.add(dockerfile.name, arcname="./Dockerfile")

            t.close()
            tmpfile.seek(0)
            yield tmpfile

    @contextmanager
    def intervention(self, container_id):
        """Ask the user if they want to commit this container and run /bin/bash in it"""
        if not self.interactive or self.heira_formatted("harpoon.no_intervention", default=False):
            yield
            return

        print("!!!!")
        print("It would appear building the image failed")
        print("Do you want to run /bin/bash where the build to help debug why it failed?")
        answer = raw_input("[y]: ")
        if answer and not answer.lower().startswith("y"):
            yield
            return

        try:
            image = self.docker_context.commit(container_id)
            image_hash = image["Id"]

            name = "{0}-intervention".format(self.name)
            self._run_container(name, image_hash, image_hash, detach=False, tty=True, command="/bin/bash", delete_on_exit=True)
            yield
        except Exception as error:
            log.error("Something failed about creating the intervention image\terror=%s", error)
            raise
        finally:
            try:
                self.docker_context.remove_image(image_hash)
            except Exception as error:
                log.error("Failed to kill intervened image\thash=%s\terror=%s", image_hash, error)

    def heira_formatted(self, key, **kwargs):
        """
        Shortcut for
        self.formatted("{0}.<key>".format(self.path), <key>, configuration=self.all_configuration, path_prefix=None)
        """
        options = {"configuration": self.all_configuration, "path_prefix": None}
        options.update(kwargs)
        return self.formatted("{0}.{1}".format(self.path, key), key, **options)

    def formatted(self, *keys, **kwargs):
        """Get us a formatted value"""
        val = kwargs.get("value", NotSpecified)
        default = kwargs.get("default", NotSpecified)
        path_prefix = kwargs.get("path_prefix", self.path)
        configuration = kwargs.get("configuration", self.configuration)

        key = ""
        if val is NotSpecified:
            for key in keys:
                if key in configuration:
                    val = configuration[key]
                    break

        if val is NotSpecified:
            if default is NotSpecified:
                raise NoSuchKey("Couldn't find any of the specified keys in image options", keys=keys, image=self.name)
            else:
                return default

        if path_prefix:
            path = "{0}.{1}".format(path_prefix, key)
        else:
            path = key

        config = MergedOptions.using(self.all_configuration, {"this": {"name": self.name, "path": self.path}})
        return MergedOptionStringFormatter(config, path, value=val).format()

    def formatted_list(self, *keys, **kwargs):
        """Get us a formatted list of values"""
        val = kwargs.get("val", NotSpecified)

        for key in keys:
            if key in self.configuration:
                val = self.configuration[key]
                if isinstance(val, basestring):
                    val = [val]
                elif not isinstance(val, list):
                    raise BadOption("Expected key to be a list", path="{0}.{1}".format(self.path, key), found=type(val))

                result = []
                for v in val:
                    kwargs["value"] = v
                    result.append(self.formatted(key, **kwargs))
                return result

        return self.formatted(*keys, **kwargs)

    def setup_configuration(self):
        """Add any generated configuration"""
        name_prefix = self.heira_formatted("image_name_prefix", default=None)
        if not isinstance(self.configuration, dict) and not isinstance(self.configuration, MergedOptions):
            raise BadImage("Image options need to be a dictionary", image=self.name)

        if "image_name" not in self.configuration:
            if name_prefix:
                image_name = "{0}-{1}".format(name_prefix, self.name)
            else:
                image_name = self.name
            self.configuration["image_name"] = image_name

        image_index = self.heira_formatted("image_index", default=None)
        if image_index:
            self.configuration["image_name"] = "{0}{1}".format(image_index, self.configuration["image_name"])

        if "container_name" not in self.configuration:
            self.configuration["container_name"] = "{0}-{1}".format(self.configuration["image_name"].replace("/", "--"), str(uuid.uuid1()).lower())

    def setup(self):
        """Setup this Image instance from configuration"""
        if "commands" not in self.configuration:
            raise NoSuchKey("Image configuration doesn't contain commands option", image=self.name, found=self.configuration.keys())

        self.parent_dir = self.heira_formatted("parent_dir", default=self.all_configuration["config_root"])
        if not os.path.exists(self.parent_dir):
            raise BadOption("Parent dir for image doesn't exist", parent_dir=self.parent_dir, image=self.name)
        self.parent_dir = os.path.abspath(self.parent_dir)

        for listable in ("link", "volumes_from", "volumes", "ports"):
            setattr(self, listable, self.formatted_list(listable, default=[]))
        self.volumes = self.normalise_volumes(self.volumes)
        self.extra_context = []
        self.commands = self.interpret_commands(self.configuration["commands"])

    def normalise_volumes(self, volumes):
        """Return normalised version of these volumes"""
        result = []
        for volume in self.volumes:
            if ":" not in volume:
                result.append(volume)
            else:
                volume, rest = volume.split(":", 1)
                result.append("{0}:{1}".format(os.path.abspath(os.path.normpath(volume)), rest))
        return result

    def interpret_commands(self, commands):
        """Return the commands as a list of strings to go into a docker file"""
        result = []
        errors = []
        for command in commands:
            if isinstance(command, basestring):
                result.append(command)
            elif isinstance(command, list):
                if len(command) != 2:
                    errors.append(BadCommand("Command spec as a list can only be two items", found_length=len(command), found=command, image=self.name))

                name, value = command
                if not isinstance(name, basestring):
                    errors.append(BadCommand("Command spec must have a string value as the first option", found=command, iamge=self.name))
                    continue

                if isinstance(value, basestring):
                    value = [self.formatted("commands", value=value)]

                if isinstance(value, dict) or isinstance(value, MergedOptions):
                    try:
                        result.extend(list(self.complex_command_spec(name, value)))
                    except BadCommand as error:
                        errors.append(error)

                else:
                    for thing in value:
                        result.append("{0} {1}".format(name, thing))
            else:
                errors.append(BadCommand("Command spec must be a string or a list", found=command, image=self.name))

        if errors:
            raise BadCommand("Command spec had errors", image=self.name, _errors=errors)

        return result

    def complex_command_spec(self, name, value):
        """Turn a complex command spec into a list of "KEY VALUE" strings"""
        if name == "ADD":
            if "content" in value:
                if "dest" not in value:
                    raise BadOption("When doing an ADD with content, must specify dest", image=self.name, command=[name, value])
                dest = value.get("dest")
                context_name = str(uuid.uuid1())
                self.extra_context.append((value.get("content"), context_name))
                yield "ADD {0} {1}".format(context_name, dest)
            else:
                prefix = value.get("prefix", "/")
                if "get" not in value:
                    raise BadOption("Command spec didn't contain 'get' option", command=[name, value], image=self.name)

                get = value["get"]
                if isinstance(get, basestring):
                    get = [get]
                elif not isinstance(get, list):
                    raise BadOption("Command spec value for 'get' should be string or a list", command=[name, value], image=self.name)

                for val in get:
                    yield "ADD {0} {1}/{2}".format(val, prefix, val)
        else:
            raise BadOption("Don't understand dictionary value for spec", command=[name, value], image=self.name)

class Imager(object):
    """Knows how to build and run docker images"""
    def __init__(self, configuration, docker_context, interactive=True, silent_build=False):
        self.interactive = interactive
        self.silent_build = silent_build
        self.configuration = configuration
        self.docker_context = docker_context

    @property
    def images(self):
        """Make our image objects"""
        if not getattr(self, "_images", None):
            if any('.' in key for key in self.configuration["images"].keys()):
                illegal = [key for key in self.configuration["images"].keys() if '.' in key]
                raise HarpoonError("Sorry, a limitation with option_merge means we can't have dots in key names", illegal=illegal)

            options = {"docker_context": self.docker_context, "interactive": self.interactive, "silent_build": self.silent_build}
            images = dict((key, Image(key, self.configuration, "images.{0}".format(key), **options)) for key, val in self.configuration["images"].items())
            for image in images.values():
                image.setup_configuration()
            for image in images.values():
                image.setup()

            self._images = images
        return self._images

    def run(self, image, command=None, env=None, volumes=None, ports=None):
        """Make this image and run it"""
        self.make_image(image)
        try:
            self.images[image].run_container(self.images, command=command, extra_env=env, extra_volumes=volumes, extra_ports=ports)
        except DockerAPIError as error:
            raise BadImage("Failed to start the container", error=error)

    def make_image(self, image, chain=None, made=None):
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

        for dependency in images[image].dependency_images(images):
            self.make_image(dependency, chain=chain + [image], made=made)

        # Should have all our dependencies now
        instance = images[image]
        log.info("Making image for '%s' (%s) - FROM %s", instance.name, instance.image_name, instance.parent_image)
        instance.build_image()
        made[image] = True

