"""
This module contains object representing the different options in an image.

These objects are responsible for understanding different conditions around the
use of these options.
"""

from harpoon.errors import BadImage, HarpoonError
from harpoon.ship.context import ContextBuilder
from harpoon.ship.builder import Builder
from harpoon.ship.runner import Runner
from harpoon.errors import BadOption
from harpoon import helpers as hp

from docker.errors import APIError as DockerAPIError
from input_algorithms.spec_base import NotSpecified
from input_algorithms.dictobj import dictobj
from contextlib import contextmanager
import logging
import uuid
import time
import six
import os

log = logging.getLogger("harpoon.option_spec.image_objs")

class Image(dictobj):
    fields = {
          "env": "Environment options"
        , "cpu": "CPU options"
        , "vars": "Arbritrary dictionary of values"
        , "name": "The name of the image"
        , "bash": "A command to run, will transform into ``bash -c '<bash>'``"
        , "user": "The user to use inside the container"
        , "ports": "The ports to expose"
        , "mtime": "The mtime of the Dockerfile"
        , "links": "The containers to link into this container"
        , "context": "The context options for building the container"
        , "devices": "Devices to add to the container"
        , "volumes": "Extra volumes to mount in the container"
        , "network": "Network options"
        , "command": "The default command for the image"
        , "harpoon": "The harpoon object"
        , "commands": "The commands that make up the Dockerfile for this image"
        , "lxc_conf": "The location to an lxc_conf file"
        , "key_name": "The name of the key this image was defined with in the configuration"
        , "recursive": "Options to allow this container be built recursively on itself"
        , "image_name": "The name of the image that is to be built"
        , "privileged": "Gives the container full access to the host"
        , "image_index": "The index and prefix to push to. i.e. ``my_registry.com/myapp/``"
        , "squash_after": "Either a boolean or list of docker commands. Signifying that we want to use docker-squash after every build"
        , "configuration": "The root configuration"
        , "other_options": "Other options to use in docker commands"
        , "wait_condition": "Wait for this condition to resolve before starting other containers"
        , "restart_policy": "The behaviour to apply when the container exists"
        , "container_name": "The name to give to the running container"
        , "deleteable_image": "Whether this image can be deleted after use"
        , "image_name_prefix": "The prefix given to the name of the image"
        , "dependency_options": "Any options to apply to our dependency containers"
        , "squash_before_push": "Either a boolean or list of docker commands. Signifying that we want to use docker-squash before pushing an image"
        }

    def __repr__(self):
        return "<Image {0}>".format(self.image_name)

    def __str__(self):
        return "{IMAGE:{0}}".format(self.image_name)

    def post_setup(self):
        for key in ('bash', 'command'):
            if getattr(self, key, NotSpecified) is not NotSpecified:
                setattr(self, key, getattr(self, key)())
        if getattr(self, 'recursive', NotSpecified) is not NotSpecified:
            self.recursive.setup_lines()

    @property
    def from_name(self):
        if getattr(self, "_from_name", NotSpecified) is NotSpecified:
            return self.image_name
        else:
            return self._from_name

    @from_name.setter
    def from_name(self, val):
        self._from_name = val

    @property
    def image_name(self):
        """
        The image_name of a container is the concatenation of the ``image_index``,
        ``image_name_prefix``, and ``name`` of the image.
        """
        if getattr(self, "_image_name", NotSpecified) is NotSpecified:
            if self.image_name_prefix:
                self._image_name = "{0}-{1}".format(self.image_name_prefix, self.name)
            else:
                self._image_name = self.name

            if self.image_index:
                self._image_name = "{0}{1}".format(self.image_index, self._image_name)
        return self._image_name

    @image_name.setter
    def image_name(self, val):
        self._image_name = val

    @property
    def container_name(self):
        """
        The container_name is the concatenation of ``image_name`` and a uuid1 string

        We also remove the url portion of the ``image_name`` before using it.
        """
        if getattr(self, "_container_name", NotSpecified) is NotSpecified:
            self.container_name = "{0}-{1}".format(self.image_name.replace("/", "--"), str(uuid.uuid1()).lower())
        return self._container_name

    @property
    def container_id(self):
        """
        Find a container id

        If one isn't already set, we ask docker for the container whose name is
        the same as the recorded container_name
        """
        if getattr(self, "_container_id", None):
            return self._container_id

        try:
            containers = self.harpoon.docker_context.containers(all=True)
        except ValueError:
            log.warning("Failed to get a list of active docker files")
            containers = []

        self._container_id = None
        for container in containers:
            if any(self.name in container.get("Names", []) for name in (self.container_name, "/{0}".format(self.container_name))):
                self._container_id = container["Id"]
                break

        return self._container_id

    @container_id.setter
    def container_id(self, container_id):
        self._container_id = container_id

    @property
    def formatted_command(self):
        """
        If we have ``bash``, then the command is ``/bin/bash -c <bash>``, whereas
        if the ``command`` is set, then we just return that.
        """
        if self.bash is not NotSpecified:
            return "/bin/bash -c '{0}'".format(self.bash)
        elif self.command is not NotSpecified:
            return self.command
        else:
            return None

    @container_name.setter
    def container_name(self, val):
        self._container_name = val

    def dependencies(self, images):
        """Yield just the dependency images"""
        if not isinstance(self.commands.parent_image, six.string_types):
            yield self.commands.parent_image.name

        for image, _ in self.dependency_images():
            yield image

    def dependency_images(self):
        """
        What images does this one require

        Taking into account parent image, and those in link and volumes.share_with options
        """
        candidates = []
        detach = dict((candidate, not options.attached) for candidate, options in self.dependency_options.items())

        for link in self.links:
            if link.container:
                candidates.append(link.container.name)

        candidates.extend(list(self.shared_volume_containers()))

        done = []
        for candidate in candidates:
            if candidate not in done:
                done.append(candidate)
                yield candidate, detach.get(candidate, True)

    def shared_volume_containers(self):
        """All the harpoon containers in volumes.share_with for this container"""
        for container in self.volumes.share_with:
            if not isinstance(container, six.string_types):
                yield container.name

    def find_missing_env(self):
        """Find any missing environment variables"""
        missing = []
        for e in self.env:
            if e.default_val is None and e.set_val is None:
                if e.env_name not in os.environ:
                    missing.append(e.env_name)

        if missing:
            raise BadOption("Some environment variables aren't in the current environment", missing=missing)

    def display_line(self):
        """A single line describing this image"""
        msg = ["Image {0}".format(self.name)]
        if self.image_index:
            msg.append("Pushes to {0}".format(self.image_name))
        return ' : '.join(msg)

    @property
    def mtime(self):
        """Mtime is set as a function to make it lazily computed via this property"""
        if callable(self._mtime):
            self._mtime = self._mtime()

        if self._mtime not in (NotSpecified, None) and type(self._mtime) is not int:
            self._mtime = int(self._mtime)

        return self._mtime

    @mtime.setter
    def mtime(self, val):
        self._mtime = val

    def build_and_run(self, images):
        """Make this image and run it"""
        Builder().make_image(self, images)

        try:
            Runner().run_container(self, images)
        except DockerAPIError as error:
            raise BadImage("Failed to start the container", error=error)

    @property
    def docker_file(self):
        if getattr(self, "_docker_file", NotSpecified) is NotSpecified:
            self._docker_file = DockerFile(self.commands.docker_lines_list, self.mtime)
        return self._docker_file

    @docker_file.setter
    def docker_file(self, val):
        self._docker_file = val

    def add_docker_file_to_tarfile(self, docker_file, tar):
        """Add a Dockerfile to a tarfile"""
        with hp.a_temp_file() as dockerfile:
            log.debug("Context: ./Dockerfile")
            dockerfile.write("\n".join(docker_file.docker_lines).encode('utf-8'))
            dockerfile.seek(0)
            os.utime(dockerfile.name, (docker_file.mtime, docker_file.mtime))
            tar.add(dockerfile.name, arcname="./Dockerfile")

    @contextmanager
    def make_context(self, docker_file=None):
        """Determine the docker lines for this image"""
        kwargs = {"silent_build": self.harpoon.silent_build, "extra_context": self.commands.extra_context}
        if docker_file is None:
            docker_file = self.docker_file
        with ContextBuilder().make_context(self.context, **kwargs) as ctxt:
            self.add_docker_file_to_tarfile(docker_file, ctxt.t)
            yield ctxt

class Recursive(dictobj):
    """Options to make an image be built recursively"""
    fields = {
          "action": "The action that we are repeating"
        , "persist": "The folders to persist between builds"
        , "image_name": "A function that returns the image name of the recursive container"
        }

    def setup_lines(self):
        """
        Setup convenience lines for copying and waiting for copying
        This setup_lines gets called by Image.post_setup, which gets called by OptionMerge conversion magic
        We also call it in the dockerfile makers for good measure
        """
        if getattr(self, "_setup_lines", None):
            return
        self._setup_lines = True

        # Make the shared volume name same as this image name so it doesn't change every time
        shared_name = self["shared_name"] = self.image_name().replace('/', '__')

        # Excuse the $(echo $volume), it's to avoid problems
        self["copy_line"] = '''
            for volume in {0}; do
                 echo "\r$(date) - Recursive: untarring $volume ($(du -sh /{1}/$(echo $volume).tar | cut -f1))";

                 mkdir -p "/{1}/$volume" "$volume"
              && tar xPf "/{1}/$(echo $volume).tar" "$volume/"
            ;done
        '''.replace("\n", "").format(' '.join('"{0}"'.format(v) for v in self.persist), shared_name)

        self["copy_to_shared_line"] = '''
            for volume in {0}; do
                 echo "\r$(date) - Recursive: Copying $volume ($(du -sh $volume | cut -f1))";

                 mkdir -p "$volume/" "/{1}/$volume"
              && tar cPf "/{1}/$(echo $volume).tar" "$volume/"
            ;done
        '''.replace("\n", "").format(' '.join('"{0}"'.format(v) for v in self.persist), shared_name)

        self["waiter_line"] = '''
            echo "\r$(date) - Recursive: Waiting for /{0}/__harpoon_provider_done__";
            export START=$(expr $(date +%s) - 5);
            while [[ ! -e /{0}/__harpoon_provider_done__ ]]; do
              (( $(expr $(date +%s) - $START) > 600 )) && exit 1 || sleep 1
            ;done
        '''.replace("\n", "").format(shared_name)

        self["precmd"] = "{0} && {1}".format(self["waiter_line"], self["copy_line"])
        self["rmcmd"] = '''echo "\r$(date) - Recursive: Removing /{0} because docker does not" && rm -rf /{0}/*'''.format(shared_name)
        self["copy_and_stay_cmd"] = "{0} && touch /{1}/__harpoon_provider_done__ && echo \"$(date) - Recursive: made /{1}/__harpoon_provider_done__\" && while true; do sleep 1; done".format(self.copy_to_shared_line, self.shared_name)

    def make_first_dockerfile(self, docker_file):
        self.setup_lines()
        docker_lines = docker_file.docker_lines + [
              "RUN bash -c '{0}'".format(self.action)
            ]
        return DockerFile(docker_lines=docker_lines, mtime=docker_file.mtime)

    def make_provider_dockerfile(self, docker_file, image_name):
        self.setup_lines()
        docker_lines = [
              "FROM {0}".format(image_name)
            , "VOLUME /{0}".format(self.shared_name)
            , "CMD /bin/bash -c '{0}'".format(self.copy_and_stay_cmd)
            ]
        return DockerFile(docker_lines=docker_lines, mtime=docker_file.mtime)

    def make_changed_dockerfile(self, docker_file, image_name):
        self.setup_lines()
        docker_lines = [
              "FROM {0}".format(image_name)
            ] + [line for line in docker_file.docker_lines if not line.startswith("FROM")] + [
              "RUN bash -c '{0}'".format(self.action)
            , "VOLUME /{0}".format(self.shared_name)
            , "CMD /bin/bash -c '{0}'".format(self.copy_and_stay_cmd)
            ]
        return DockerFile(docker_lines=docker_lines, mtime=docker_file.mtime)

    def make_builder_dockerfile(self, docker_file):
        self.setup_lines()
        docker_lines = docker_file.docker_lines + [
              "CMD /bin/bash -c '{0} && {1} && {2}'".format(self.waiter_line, self.copy_line, self.rmcmd)
            ]
        return DockerFile(docker_lines=docker_lines, mtime=docker_file.mtime)

class DockerFile(dictobj):
    """Understand about the dockerfile"""
    fields = ["docker_lines", "mtime"]

class WaitCondition(dictobj):
    """Options for waiting for images"""
    class KeepWaiting: pass
    class Timedout: pass

    fields = {
          "harpoon": "Access to the harpoon object"
        , ("timeout", 300): "How many seconds till we stop waiting altogether"
        , ("wait_between_attempts", 10): "How many seconds to wait between attempts"

        , "greps": "A dictionary of filename to a regex of what to expect in the file"
        , "command": "A list of commands to run"
        , "port_open": "A list of ports to look for"
        , "file_value": "A dictionary of filename to expected content"
        , "curl_result": "A dictionary of urls and expected content from the url"
        , "file_exists": "A list of files to look for"
        }

    def conditions(self, start, last_attempt):
        """
        Yield lines to execute in a docker context

        All conditions must evaluate for the container to be considered ready
        """
        if time.time() - start > self.timeout:
            yield WaitCondition.Timedout
            return

        if last_attempt is not None and time.time() - last_attempt < self.wait_between_attempts:
            yield WaitCondition.KeepWaiting
            return

        if self.greps is not NotSpecified:
            for name, val in self.greps.items():
                yield 'grep "{0}" "{1}"'.format(val, name)

        if self.file_value is not NotSpecified:
            for name, val in self.file_value.items():
                command = 'diff <(echo {0}) <(cat {1})'.format(val, name)
                if not self.harpoon.debug:
                    command = "{0} > /dev/null".format(command)
                yield command

        if self.port_open is not NotSpecified:
            for port in self.port_open:
                yield 'nc -z 127.0.0.1 {0}'.format(port)

        if self.curl_result is not NotSpecified:
            for url, content in self.curl_result.items():
                yield 'diff <(curl "{0}") <(echo {1})'.format(url, content)

        if self.file_exists is not NotSpecified:
            for path in self.file_exists:
                yield 'cat {0} > /dev/null'.format(path)

        if self.command is not NotSpecified:
            for command in self.command:
                yield command

class Context(dictobj):
    """Understand how to build the context for a container"""
    fields = {
          "enabled": "Whether building a context is enabled or not"
        , "parent_dir": "The parent directory to get the context from (this is an absolute path, use ``{config_root}`` to make it relative to the configuration)"
        , ("include", None): "Globs of what to include in the context"
        , ("exclude", None): "Globs of what to exclude from the context"
        , ("use_gitignore", lambda: NotSpecified): "Whether we should pay attention to git ignore logic"
        , ("use_git_timestamps", lambda: NotSpecified): "Whether we should find commit timestamps for the files in the context"
        }

    @property
    def parent_dir(self):
        return self._parent_dir

    @parent_dir.setter
    def parent_dir(self, val):
        self._parent_dir = os.path.abspath(val)

    @property
    def use_git(self):
        use_git = False
        if self._use_gitignore is not NotSpecified and self._use_gitignore:
            use_git = True
        if self._use_git_timestamps is not NotSpecified and self._use_git_timestamps:
            use_git = True
        return use_git

    @property
    def use_git_timestamps(self):
        return self.use_git if self._use_git_timestamps is NotSpecified else self._use_git_timestamps

    @use_git_timestamps.setter
    def use_git_timestamps(self, val):
        self._use_git_timestamps = val

    @property
    def use_gitignore(self):
        return False if self._use_gitignore is NotSpecified else self._use_gitignore

    @use_gitignore.setter
    def use_gitignore(self, val):
        self._use_gitignore = val

    @property
    def git_root(self):
        """
        Find the root git folder
        """
        if not getattr(self, "_git_folder", None):
            root_folder = os.path.abspath(self.parent_dir)
            while not os.path.exists(os.path.join(root_folder, '.git')):
                if root_folder == '/':
                    raise HarpoonError("Couldn't find a .git folder", start_at=self.parent_dir)
                root_folder = os.path.dirname(root_folder)
            self._git_folder = root_folder
        return self._git_folder

class Link(dictobj):
    """Holds specification for containers that are to be linked at runtime"""
    fields = ["container", "container_name", "link_name"]

    @property
    def pair(self):
        return (self.container_name, self.link_name)

class Volumes(dictobj):
    """Holds specification of what volumes to mount/share with a container"""
    fields = {
          "mount": "Volumes to mount into this container"
        , "share_with": "Containers to share volumes with"
        }

    @property
    def share_with_names(self):
        """The names of the containers that we share with the running container"""
        for container in self.share_with:
            if isinstance(container, six.string_types):
                yield container
            else:
                yield container.container_name

    @property
    def volume_names(self):
        """Return just the volume names"""
        return [mount.container_path for mount in self.mount]

    @property
    def binds(self):
        """Return the bind options for these volumes"""
        return dict(mount.pair for mount in self.mount)

class Mount(dictobj):
    """A single mount location for a running container"""
    fields = ["local_path", "container_path", "permissions"]

    @property
    def pair(self):
        if self.permissions == 'rw':
            return (self.local_path, {"bind": self.container_path, 'ro': False})
        else:
            return (self.local_path, {"bind": self.container_path, 'ro': True})

class Environment(dictobj):
    """A single environment variable, and it's default or set value"""
    fields = ["env_name", ("default_val", None), ("set_val", None)]

    @property
    def pair(self):
        """Get the name and value for this environment variable"""
        if self.set_val is not None:
            return self.env_name, self.set_val
        elif self.default_val is not None:
            return self.env_name, os.environ.get(self.env_name, self.default_val)
        else:
            return self.env_name, os.environ[self.env_name]

class Port(dictobj):
    """A port binding specification"""
    fields = ["ip", "host_port", "container_port"]

    @property
    def pair(self):
        """return (container_port, (ip, host_port)) or (container_port, host_port)"""
        if self.ip is NotSpecified:
            if self.ip is NotSpecified:
                second = self.host_port
            else:
                second = (self.ip, )
        else:
            second = (self.ip, self.host_port)
        return self.container_port.port_str, second

class ContainerPort(dictobj):
    """The port and transport specification for a port in a running container"""
    fields = ["port", ("transport", lambda: NotSpecified)]

    @property
    def port_pair(self):
        """The port and it's transport as a pair"""
        if self.transport is NotSpecified:
            return self.port
        else:
            return (self.port, self.transport)

    @property
    def port_str(self):
        """The port and it's transport as a single string"""
        if self.transport is NotSpecified:
            return str(self.port)
        else:
            return "{0}/{1}".format(self.port, self.transport)

class Network(dictobj):
    """Network options"""
    fields = {
          "dns": "A list of dns servers for the container to use"
        , "mode": "Sets the networking mode for the container"
        , "hostname": "The desired hostname to use for the container"
        , "disabled": "Whether the network is disabled"
        , "dns_search": "A list of DNS search domains"
        , "domainname": "The desired domain name to use for the containe"
        , "extra_hosts": "A list of hostnames/IP mappings to be added to the container's /etc/hosts file"
        , "publish_all_ports": "Allocates a random host port for all of a container's exposed ports"
        }

class DependencyOptions(dictobj):
    """Options for dependency containers"""
    fields = {
          "wait_condition": "Dictionary of image name to wait_conditions. These override wait conditions on the dependency itself"
        , ("attached", False): "Whether harpoon attaches to this container or not"
        }

class Cpu(dictobj):
    """Cpu options"""
    fields = {
          "cpuset": "cgroups Cpuset to use"
        , "cap_add": "List of kernel capabilties to add to the container"
        , "cap_drop": "List of kernel capabilties to drop from the container"
        , "mem_limit": "Memory limit in bytes"
        , "cpu_shares": "The CPU Shares for container (ie. the relative weight vs othercontainers)"
        , "memswap_limit": "Total memory usage (memory + swap); set -1 to disable swap"
        }

