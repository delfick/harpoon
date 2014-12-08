from harpoon.formatter import MergedOptionStringFormatter
from harpoon.errors import DeprecatedFeature

from input_algorithms.spec_base import NotSpecified
from harpoon.errors import BadCommand, BadOption
from input_algorithms.dictobj import dictobj
import hashlib
import uuid
import os

class Image(dictobj):
    fields = [
          "commands", "links", "context"
        , "lxc_conf", "volumes", "env", "ports"
        , "other_options", "network", "privileged", "name_prefix"
        , "image_name", "image_index", "dependency_options"
        , "container_name", "name", "key_name"
        ]

    @property
    def image_name(self):
        if getattr(self, "_image_name", NotSpecified) is NotSpecified:
            if self.name_prefix:
                self._image_name = "{0}-{1}".format(self.name_prefix, self.name)
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
        if getattr(self, "_container_name", NotSpecified) is NotSpecified:
            self.container_name = "{0}-{1}".format(self.image_name.replace("/", "--"), str(uuid.uuid1()).lower())
        return self._container_name

    @property
    def formatted_command(self):
        if self.bash:
            return "/bin/bash -c '{0}'".format(self.bash)
        else:
            return self.command

    @container_name.setter
    def container_name(self, val):
        self._container_name = val

    def dependencies(self, images):
        """Yield just the dependency images"""
        for image, _ in self.dependency_images(images):
            yield image

    def dependency_images(self, images, ignore_parent=False):
        """
        What images does this one require

        Taking into account parent image, and those in link and volumes.share_with options
        """
        candidates = []
        detach = dict((candidate, not options.attached) for candidate, options in self.dependency_options.items())

        if not ignore_parent:
            if not isinstance(self.commands.parent_image, basestring):
                candidates.append(self.commands.parent_image.name)

        for link in self.links:
            if link.container:
                candidates.append(link.container)

        for container in self.volumes.share_with:
            if not isinstance(container, basestring):
                candidates.append(container)

        done = set()
        for candidate in candidates:
            if candidate not in done:
                done.add(candidate)
                yield candidate, detach.get(candidate, True)

    def find_missing_env(self):
        """Find any missing environment variables"""
        missing = []
        for e in self.env:
            if not e.default_val and not e.set_val:
                if e.env_name not in os.environ:
                    missing.append(e.env_name)

        if missing:
            raise BadOption("Some environment variables aren't in the current environment", missing=missing)

class Command(dictobj):
    fields = ['meta', 'orig_command']

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.extra_context = []

    @property
    def commands(self):
        if not getattr(self, "_commands", None):
            self._commands = []
            for command in self.orig_command:
                for cmd in self.determine_commands(self.meta, command):
                    self._commands.append(cmd)
        return self._commands

    @property
    def parent_image(self):
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
        if isinstance(parent, basestring):
            return parent
        else:
            return parent.image_name

    def docker_file(self):
        res = []
        for name, value in self.commands:
            if name == "FROM" and not isinstance(value, basestring):
                value = value.image_name
            res.append("{0} {1}".format(name, value))

        return '\n'.join(res)


    def determine_commands(self, meta, command):
        errors = []
        if not command:
            return

        elif isinstance(command, (str, unicode)):
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
        if not isinstance(name, basestring):
            errors.append(BadCommand("Command spec must have a string value as the first option", found=command))
        elif isinstance(value, basestring):
            if name == "FROM" and value.endswith(".image_name}"):
                raise DeprecatedFeature("Just specify the image in the FROM, not it's image_name", value=value, meta=meta)

            value = [MergedOptionStringFormatter(meta.everything, "commands", value=value).format()]
            if name == "FROM":
                if not isinstance(value, basestring):
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
                if isinstance(get, basestring):
                    get = [get]
                elif not isinstance(get, list):
                    raise BadOption("Command spec value for 'get' should be string or a list", command=[name, value], image=self.name)

                for val in get:
                    yield "ADD", "{0} {1}/{2}".format(val, prefix, val)
        else:
            raise BadOption("Don't understand dictionary value for spec", command=[name, value], image=self.name)

class Link(dictobj):
    fields = ["container_name", "link_name"]

    def pair(self):
        return (self.container_name, self.link_name)

class Context(dictobj):
    fields = ["include", "exclude", "enabled", "parent_dir", "use_gitignore", "use_git_timestamps"]

class Volumes(dictobj):
    fields = ["mount", "share_with"]

    @property
    def share_with_names(self):
        for container in self.share_with:
            if isinstance(container, basestring):
                yield container
            else:
                yield container.container_name

    def mount_options(self):
        return [mount.options() for mount in self.mount]

class Mount(dictobj):
    fields = ["local_path", "container_path", "permissions"]

    def options(self):
        return (self.local_path, self.container_path, self.permissions)

class Environment(dictobj):
    fields = ["env_name", ("default_val", None), ("set_val", None)]

    def pair(self):
        """Get the name and value for this environment variable"""
        if self.set_val:
            return self.env_name, self.set_val
        elif self.default_val:
            return self.env_name, os.environ.get(self.env_name, self.default_val)
        else:
            return self.env_name, os.environ[self.env_name]

class Port(dictobj):
    fields = ["port"]

class Network(dictobj):
    fields = ["dns", "mode", "hostname", "disabled", "dns_search", "publish_all_ports"]

class DependencyOptions(dictobj):
    fields = [("attached", False)]

