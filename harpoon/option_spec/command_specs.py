"""
It's recommended you read this file from the bottom up.
"""

from harpoon.formatter import MergedOptionStringFormatter
from harpoon.option_spec.command_objs import Command
from harpoon.errors import BadOption

from input_algorithms.many_item_spec import many_item_formatted_spec
from input_algorithms.spec_base import NotSpecified
from input_algorithms import spec_base as sb
from input_algorithms import validators

import hashlib
import six

class complex_ADD_spec(sb.Spec):
    def normalise(self, meta, val):
        if "content" in val:
            spec = sb.set_options(mtime=sb.optional_spec(sb.integer_spec()), dest=sb.required(sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)), content=sb.string_spec())
            result = spec.normalise(meta, val)
            mtime = result["mtime"]
            if mtime is NotSpecified:
                mtime = meta.everything["mtime"]()
            context_name = "{0}-{1}-mtime({2})".format(hashlib.md5(result['content'].encode('utf-8')).hexdigest(), result["dest"].replace("/", "-").replace(" ", "--"), mtime)
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
    specs = [
          # First item is just a string
          sb.string_spec()

          # Second item is a required list of either dicts or strings
        , sb.required( sb.listof( sb.match_spec(
              (dict, complex_ADD_spec())
            , (six.string_types + (list, ), sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter))
            )))
        ]

    def create_result(self, action, command, meta, val, dividers):
        if callable(command) or isinstance(command, six.string_types):
            command = [command]

        result = []
        for cmd in command:
            if not isinstance(cmd, list):
                cmd = [cmd]

            for c in cmd:
                if isinstance(c, Command):
                    result.append(c)
                else:
                    result.append(Command((action, c)))
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

# Only support ADD commands for the dictionary representation atm
dict_key = sb.valid_string_spec(validators.choice("ADD"))
dictionary_command_spec = lambda: convert_dict_command_spec(sb.dictof(dict_key, complex_ADD_spec()))

# The main spec
# We match against, strings, lists, dictionaries and Command objects with different specs
command_spec = lambda: sb.match_spec(
      (six.string_types, string_command_spec())
    , (list, array_command_spec())
    , (dict, dictionary_command_spec())
    , (Command, sb.any_spec())
    )

