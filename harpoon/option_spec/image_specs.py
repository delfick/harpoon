from harpoon.option_spec.image_objs import Link, Command, Mount, Environment
from harpoon.option_spec.specs import many_item_formatted_spec
from harpoon.formatter import MergedOptionStringFormatter

from input_algorithms.spec_base import string_spec, Spec

class any_spec(object):
    def normalise(self, meta, val):
        return val

port_spec = any_spec

class command_spec(Spec):
    def normalise(self, meta, command):
        return Command(self.determine_commands(meta, command))

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
            if isinstance(value, basestring):
                value = [MergedOptionStringFormatter("commands", meta.path, value=value)]

        if isinstance(value, dict) or isinstance(value, MergedOptions):
            try:
                for part in self.complex_spec(name, value):
                    yield part
            except BadCommand as error:
                errors.append(error)
        else:
            for part in value:
                yield "{0} {1}".format(name, part)
            else:
                errors.append(BadCommand("Command spec must be a string or a list", found=command))

        if errors:
            raise BadCommand("Command spec had errors", path=meta.path, source=meta.source, _errors=errors)

    def complex_spec(self, name, value):
        raise NotImplementedError()

class mount_spec(many_item_formatted_spec):
    value_name = "Volume mounting"
    specs = [string_spec, string_spec]
    optional_specs = [string_spec]
    formatter = MergedOptionStringFormatter

    def create_result(self, local_path, container_path, permissions, meta, val):
        if permissions is NotSpecified:
            permissions = 'rw'
        return Mount(local_path, container_path, permissions)

class env_spec(many_item_formatted_spec):
    value_name = "Environment Variable"
    specs = [string_spec()]
    optional_specs = [string_spec()]
    formatter = MergedOptionStringFormatter

    def create_result(self, env_name, default_val, meta, val):
        return Environment(env_name, default_val)

class link_spec(many_item_formatted_spec):
    value_name = "Container link"
    specs = [string_spec]
    optional_specs = [string_spec]
    formatter = MergedOptionStringFormatter

    def determine_2(self, container_name, meta, val):
        return container_name[container_name.rfind(":")+1:].replace('/', '-')

    def alter_1(self, container_name, meta, val):
        if isinstance(container_name, Image):
            return container_name.container_name
        return container_name

    def create_result(self, container_name, link_name, meta, val):
        return Link(container_name, link_name)

