from harpoon.option_spec.specs import many_item_formatted_spec
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.option_spec.command_objs import Command
from harpoon.errors import BadOption

from input_algorithms import spec_base as sb
from input_algorithms import validators

import hashlib
import six

class complex_ADD_spec(sb.Spec):
    def normalise(self, meta, val):
        if "content" in val:
            spec = sb.set_options(dest=sb.required(sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)), content=sb.string_spec())
            result = spec.normalise(meta, val)
            context_name = "{0}-{1}".format(hashlib.md5(result['content'].encode('utf-8')).hexdigest(), result["dest"].replace("/", "-").replace(" ", "--"))
            return Command(("ADD", "{0} {1}".format(context_name, result["dest"])), (result["content"], context_name))
        else:
            spec = sb.set_options(
                  get=sb.required(sb.listof(sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)))
                , prefix = sb.defaulted(sb.string_spec(), "")
                )
            result = spec.normalise(meta, val)

            final = []
            for val in result["get"]:
                final.append(Command(("ADD", "{0} {1}/{2}".format(val, result["prefix"], val))))
            return final

class array_command_spec(many_item_formatted_spec):
    value_name = "Command"
    as_list = sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)
    specs = [sb.string_spec(), sb.match_spec((six.string_types + (list, ), as_list), (dict, complex_ADD_spec()))]

    def spec_wrapper_2(self, spec, action, command, meta, val, dividers):
        if action == "FROM":
            spec = sb.listof(sb.delayed(spec))
        elif type(command) is not dict:
            spec = sb.listof(spec)
        return sb.required(spec)

    def create_result(self, action, command, meta, val, dividers):
        if callable(command) or isinstance(command, six.string_types):
            command = [command]

        result = []
        for cmd in command:
            if isinstance(cmd, Command):
                result.append(cmd)
            else:
                result.append(Command((action, cmd)))
        return result

class convert_dict_command_spec(sb.Spec):
    def setup(self, spec):
        self.spec = spec

    def normalise(self, meta, val):
        result = []
        for val in self.spec.normalise(meta, val).values():
            if isinstance(val, Command):
                result.append(val)
            else:
                result.extend(val)
        return result

class has_a_space(validators.Validator):
    def validate(self, meta, val):
        if ' ' not in val:
            raise BadOption("Expected string to have a space (<ACTION> <COMMAND>)", meta=meta, got=val)
        return val

string_command_spec = lambda: sb.container_spec(Command, sb.valid_string_spec(has_a_space()))
dictionary_command_spec = lambda: convert_dict_command_spec(sb.dictof(sb.valid_string_spec(validators.choice("ADD")), complex_ADD_spec()))
command_spec = lambda: sb.match_spec((six.string_types, string_command_spec()), (list, array_command_spec()), (dict, dictionary_command_spec()), (Command, sb.any_spec()))

