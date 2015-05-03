"""
Custom specifications for the different types of image options.

The idea is that these understand the conditions around representation of the
options.
"""

from harpoon.option_spec.image_objs import Link, Mount, Environment, Port, ContainerPort
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.errors import BadConfiguration

from input_algorithms.many_item_spec import many_item_formatted_spec
from input_algorithms.spec_base import NotSpecified
from input_algorithms import spec_base as sb
from input_algorithms.spec_base import Spec

import six

class image_name_spec(Spec):
    def normalise_filled(self, meta, val):
        """Only care about valid image names"""
        available = list(meta.everything["images"].keys())
        val = sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter).normalise(meta, val)
        if val not in available:
            raise BadConfiguration("Specified image doesn't exist", specified=val, available=available)
        return val

class mount_spec(many_item_formatted_spec):
    value_name = "Volume mounting"
    specs = [sb.string_spec(), sb.string_spec()]
    optional_specs = [sb.string_spec()]
    formatter = MergedOptionStringFormatter

    def create_result(self, local_path, container_path, permissions, meta, val, dividers):
        """Default permissions to rw"""
        if permissions is NotSpecified:
            permissions = 'rw'
        return Mount(local_path, container_path, permissions)

class env_spec(many_item_formatted_spec):
    value_name = "Environment Variable"
    seperators = [':', '=']

    specs = [sb.string_spec()]
    optional_specs = [sb.string_or_int_as_string_spec()]
    formatter = MergedOptionStringFormatter

    def create_result(self, env_name, other_val, meta, val, dividers):
        """Set default_val and set_val depending on the seperator"""
        args = [env_name]
        if other_val is NotSpecified:
            other_val = None
        if not dividers:
            args.extend([None, None])
        elif dividers[0] == ':':
            args.extend([other_val, None])
        elif dividers[0] == '=':
            args.extend([None, other_val])
        return Environment(*args)

class link_spec(many_item_formatted_spec):
    value_name = "Container link"
    specs = [sb.string_spec()]
    optional_specs = [sb.string_spec()]
    formatter = MergedOptionStringFormatter

    def determine_2(self, container_name, container_alias, meta, val):
        """"Default the alias to the name of the container"""
        if container_alias is not NotSpecified:
            return container_alias
        return container_name[container_name.rfind(":")+1:].replace('/', '-')

    def alter_1(self, given_container_name, container_name, meta, val):
        """Get the container_name of the container if a container is specified"""
        meta.container = None
        if not isinstance(container_name, six.string_types):
            meta.container = container_name
            container_name = container_name.container_name
        return container_name

    def create_result(self, container_name, link_name, meta, val, dividers):
        return Link(meta.container, container_name, link_name)

class port_spec(many_item_formatted_spec):
    value_name = "Ports"
    specs = [sb.string_or_int_as_string_spec()]
    optional_specs = [sb.string_or_int_as_string_spec(), sb.string_or_int_as_string_spec()]
    formatter = MergedOptionStringFormatter

    def create_result(self, ip, host_port, container_port, meta, val, dividers):
        """
        The format is the same as the default docker cli client::

            ip:hostPort:containerPort | ip::containerPort | hostPort:containerPort | containerPort
        """
        if host_port in ('', NotSpecified) and container_port in ('', NotSpecified):
            container_port = ip
            ip = NotSpecified
            host_port = NotSpecified
        elif container_port in ('', NotSpecified):
            container_port = host_port
            host_port = ip
            ip = NotSpecified
        elif host_port in ('', NotSpecified):
            host_port = NotSpecified

        if host_port == '':
            host_port = NotSpecified
        if container_port == '':
            container_port = NotSpecified

        if host_port is not NotSpecified:
            host_port = sb.integer_spec().normalise(meta.indexed_at('host_port'), host_port)
        container_port = sb.required(container_port_spec()).normalise(meta.indexed_at('container_port'), container_port)

        return Port(ip, host_port, container_port)

class container_port_spec(many_item_formatted_spec):
    value_name = "Container port"
    specs = [sb.integer_spec()]
    optional_specs = [sb.string_spec()]
    formatter = MergedOptionStringFormatter
    seperators = ['/']

    def create_result(self, port, transport, meta, val, dividiers):
        return ContainerPort(port, transport)
