from harpoon.option_spec.image_objs import Link, Command, Mount
from harpoon.option_spec.specs import many_item_formatted_spec

from input_algorithms.spec_base import string_spec, Spec

class any_spec(object):
    def normalise(self, meta, val):
        return val

env_spec = any_spec
port_spec = any_spec

class command_spec(Spec):
    def normalise(self, meta, val):
        action = val[val.find(" "):].strip()
        value = val[:val.find(" ")].strip()
        return Command(action, value)

class mount_spec(many_item_formatted_spec):
    value_name = "Volume mounting"
    specs = [string_spec, string_spec]
    optional_specs = [string_spec]

    def create_result(self, local_path, container_path, permissions, meta, val):
        if permissions is NotSpecified:
            permissions = 'rw'
        return Mount(local_path, container_path, permissions)

class link_spec(many_item_formatted_spec):
    value_name = "Container link"
    specs = [string_spec]
    optional_specs = [string_spec]

    def determine_2(self, container_name, meta, val):
        return container_name[container_name.rfind(":")+1:].replace('/', '-')

    def alter_1(self, container_name, meta, val):
        if isinstance(container_name, Image):
            return container_name.container_name
        return container_name

    def create_result(self, container_name, link_name, meta, val):
        return Link(container_name, link_name)

