"""
This module contains object representing the different options in an image.

These objects are responsible for understanding different conditions around the
use of these options.
"""

from harpoon.errors import DeprecatedFeature, BadImage, HarpoonError
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.ship.context import ContextBuilder
from harpoon.ship.builder import Builder
from harpoon.ship.runner import Runner

from docker.errors import APIError as DockerAPIError
from input_algorithms.spec_base import NotSpecified
from harpoon.errors import BadCommand, BadOption
from input_algorithms.dictobj import dictobj
from contextlib import contextmanager
import logging
import hashlib
import uuid
import six
import os

log = logging.getLogger("harpoon.option_spec.image_objs")

class Image(dictobj):
    fields = [
          "commands", "links", "context", "devices"
        , "lxc_conf", "volumes", "env", "ports", "restart_policy"
        , "other_options", "network", "privileged", "image_name_prefix"
        , "image_name", "image_index", "dependency_options"
        , "container_name", "name", "key_name", "harpoon", "cpu"
        , "bash", "command", "mtime", "configuration", "user"
        ]

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

        for container in self.volumes.share_with:
            if not isinstance(container, six.string_types):
                candidates.append(container.name)

        done = []
        for candidate in candidates:
            if candidate not in done:
                done.append(candidate)
                yield candidate, detach.get(candidate, True)

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

    @contextmanager
    def make_context(self):
        docker_file = DockerFile(self.commands.docker_lines, self.mtime)
        kwargs = {"silent_build": self.harpoon.silent_build, "extra_context": self.commands.extra_context}
        with ContextBuilder().make_context(self.context, docker_file, **kwargs) as ctxt:
            yield ctxt

class Command(dictobj):
    """This holds the list of commands that make up the docker file for this image"""
    fields = ['meta', 'orig_command']

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.extra_context = []

    @property
    def commands(self):
        """Yield the expanded commands"""
        if not getattr(self, "_commands", None):
            self._commands = []
            for command in self.orig_command:
                for cmd in self.determine_commands(self.meta, command):
                    self._commands.append(cmd)
        return self._commands

    @property
    def parent_image(self):
        """Determine the parent_image from the FROM command"""
        if hasattr(self, "_commands"):
            for name, command in self._commands:
                if name == "FROM":
                    return command

        for command in self.orig_command:
            cmd = command
            if isinstance(command, dict):
                cmd = command.items()[0]

            if isinstance(command, list):
                cmd, _ = command

            if cmd.startswith("FROM"):
                val = list(self.determine_commands(self.meta, command))[0][1]
                return val

    @property
    def parent_image_name(self):
        """Return the image name of the parent"""
        parent = self.parent_image
        if isinstance(parent, six.string_types):
            return parent
        else:
            return parent.image_name

    @property
    def docker_lines(self):
        """Return the commands as a newline seperated list of strings"""
        res = []
        for name, value in self.commands:
            if name == "FROM" and not isinstance(value, six.string_types):
                value = value.image_name
            res.append("{0} {1}".format(name, value))

        return '\n'.join(res)

    def determine_commands(self, meta, command):
        """Expand a single command"""
        errors = []
        if not command:
            return

        elif isinstance(command, six.string_types):
            yield command.split(" ", 1)
            return

        if isinstance(command, dict):
            command = command.items()
            if len(command) > 1:
                errors.append(BadCommand("Command spec as a dictionary can only be one {key: val}", found_length=len(command)))

            command = command[0]

        if len(command) != 2:
            errors.append(BadCommand("Command spec as a list can only be two items", found_length=len(command), found=command))

        name, value = command
        if not isinstance(name, six.string_types):
            errors.append(BadCommand("Command spec must have a string value as the first option", found=command))
        elif isinstance(value, six.string_types):
            if name == "FROM" and value.endswith(".image_name}"):
                raise DeprecatedFeature("Just specify the image in the FROM, not it's image_name", value=value, meta=meta)

            value = [MergedOptionStringFormatter(meta.everything, "commands", value=value).format()]
            if name == "FROM":
                if not isinstance(value, six.string_types):
                    yield name, value[0]
                    return

        if isinstance(value, dict):
            try:
                for part in self.complex_spec(name, value):
                    yield part
            except BadCommand as error:
                errors.append(error)
        else:
            for part in value:
                yield name, part

            if not value:
                errors.append(BadCommand("Command spec must be a string or a list", found=command))

        if errors:
            raise BadCommand("Command spec had errors", path=meta.path, source=meta.source, _errors=errors)

    def complex_spec(self, name, value):
        """Turn a complex command spec into a list of "KEY VALUE" strings"""
        if name == "ADD":
            if "content" in value:
                if "dest" not in value:
                    raise BadOption("When doing an ADD with content, must specify dest", image=self.name, command=[name, value])
                dest = value.get("dest")
                context_name = "{0}-{1}".format(hashlib.md5(value.get('content')).hexdigest(), dest.replace("/", "-").replace(" ", "--"))
                self.extra_context.append((value.get("content"), context_name))
                yield "ADD", "{0} {1}".format(context_name, dest)
            else:
                prefix = value.get("prefix", "/")
                if "get" not in value:
                    raise BadOption("Command spec didn't contain 'get' option", command=[name, value], image=self.name)

                get = value["get"]
                if isinstance(get, six.string_types):
                    get = [get]
                elif not isinstance(get, list):
                    raise BadOption("Command spec value for 'get' should be string or a list", command=[name, value], image=self.name)

                for val in get:
                    yield "ADD", "{0} {1}/{2}".format(val, prefix, val)
        else:
            raise BadOption("Don't understand dictionary value for spec", command=[name, value], image=self.name)

class DockerFile(dictobj):
    """Understand about the dockerfile"""
    fields = ["docker_lines", "mtime"]

class Context(dictobj):
    """Understand how to build the context for a container"""
    fields = ["enabled", "parent_dir", ("include", None), ("exclude", None), ("use_gitignore", lambda: NotSpecified), ("use_git_timestamps", lambda: NotSpecified)]

    @property
    def parent_dir(self):
        return self._parent_dir

    @parent_dir.setter
    def parent_dir(self, val):
        self._parent_dir = os.path.abspath(val)

    @property
    def use_git(self):
        use_git = False
        if self.use_gitignore is not NotSpecified and self.use_gitignore:
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
    fields = ["mount", "share_with"]

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
    fields = ["dns", "mode", "hostname", "disabled", "dns_search", "publish_all_ports", "domainname", "extra_hosts"]

class DependencyOptions(dictobj):
    """Options for dependency containers"""
    fields = [("attached", False)]

class Cpu(dictobj):
    """Cpu options"""
    fields = ["cpuset", "mem_limit", "cpu_shares", "memswap_limit", "cap_add", "cap_drop"]

