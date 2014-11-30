from input_algorithms.dictobj import dictobj

class Image(dictobj):
    fields = [
          "commands", "links", "context"
        , "lxc_conf", "volumes", "env", "ports"
        , "other_options", "network", "privileged"
        , "image_name", "dependency_options"
        , "container_name", "name", "key_name"
        ]

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
            for image, instance in images.items():
                if self.commands.parent_image == instance.image_name:
                    candidates.append(image)
                    break

        for link in self.links:
            if link.container_name in managed_containers:
                candidates.append(managed_containers[link.container])

        for container in self.volumes.share_with:
            if container_name in managed_containers:
                candidates.append(managed_containers[container_name])

        done = set()
        for candidate in candidates:
            if candidate not in done:
                done.add(candidate)
                yield candidate, detach.get(candidate, True)

class Command(dictobj):
    fields = ['meta', 'orig_command']

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
            return self._commands[0].split(" ", 1)[1]

        for command in self.orig_command:
            cmd = command
            if isinstance(command, dict):
                cmd = command.items()[0]

            if isinstance(command, list):
                cmd, _ = command

            if cmd.startswith("FROM"):
                return list(self.determine_commands(self.meta, command))[0].split(" ", 1)[1]

    def determine_commands(self, meta, command):
        errors = []
        if not command:
            return

        elif isinstance(command, (str, unicode)):
            yield command
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
        else:
            value = [MergedOptionStringFormatter(meta.everything, "commands", value=value).format()]

        if isinstance(value, dict):
            try:
                for part in self.complex_spec(name, value):
                    yield part
            except BadCommand as error:
                errors.append(error)
        else:
            for part in value:
                yield "{0} {1}".format(name, part)

            if not value:
                errors.append(BadCommand("Command spec must be a string or a list", found=command))

        if errors:
            raise BadCommand("Command spec had errors", path=meta.path, source=meta.source, _errors=errors)

    def complex_spec(self, name, value):
        raise NotImplementedError()

class Link(dictobj):
    fields = ["container_name", "link_name"]

class Context(dictobj):
    fields = ["include", "exclude", "enabled", "parent_dir", "use_gitignore", "use_git_timestamps"]

class Volumes(dictobj):
    fields = ["mount", "share_with"]

class Mount(dictobj):
    fields = ["mount"]

class Environment(dictobj):
    fields = ["env_name", "default_val"]

class Port(dictobj):
    fields = ["port"]

class Network(dictobj):
    fields = ["dns", "mode", "hostname", "disabled", "dns_search", "publish_all_ports"]

class DependencyOptions(dictobj):
    fields = [("attached", False)]

