"""
It's recommended you read this file from the bottom up.
"""

from harpoon.formatter import MergedOptionStringFormatter
from harpoon.errors import BadOption, ProgrammerError
from harpoon.option_spec.command_objs import Command

from input_algorithms.many_item_spec import many_item_formatted_spec
from input_algorithms.spec_base import NotSpecified
from input_algorithms.errors import BadSpecValue
from input_algorithms import spec_base as sb
from input_algorithms.dictobj import dictobj
from input_algorithms import validators

import hashlib
import json
import six

class CommandContentAddString(dictobj):
    fields = ["content"]

    def resolve(self):
        return self.content
    for_json = resolve

class CommandContent(dictobj):
    def setup(self, *args, **kwargs):
        if self.__class__ is CommandContent:
            raise ProgrammerError("This should never be instantiated without subclassing it")
        else:
            super(CommandContent, self).setup(*args, **kwargs)

    def context_name(self, meta):
        mtime = self.mtime
        if mtime is NotSpecified:
            ctxt = type("Context", (object, ), {"use_git": True})()
            mtime = meta.everything["mtime"](ctxt)

        hsh = self.make_hash()
        dst = self.dest.replace("/", "-").replace(" ", "--")

        return "{0}-{1}-mtime({2})".format(hsh, dst, mtime)

    def make_hash(self):
        content_json = json.dumps({"content": self.for_json()}, sort_keys=True)
        return hashlib.md5(content_json.encode('utf-8')).hexdigest()

class CommandContextAdd(CommandContent):
    fields = {
          "dest": "The path in the container where the content will be put"
        , "mtime": "The modified time given to the item put into the context"
        , "context": "Context options that creates a context tar that is added into the container"
        }

    def for_json(self):
        return str(self.context.as_dict())

    def commands(self, meta):
        context_name = "{0}.tar".format(self.context_name(meta))
        extra_context = ({"context": self.context}, context_name)
        yield Command(("ADD", "{0} {1}".format(context_name, self.dest)), extra_context)

class CommandContentAdd(CommandContent):
    fields = {
          "dest": "The path in the container where the content will be put"
        , "mtime": "The modified time given to the item put into the context"
        , "content": "The content to put into the context"
        , ("formatted", None): "Formatted string for content to put into the context"
        }

    @property
    def resolved_content(self):
        return self.content if self.content is not sb.NotSpecified else self.formatted

    def for_json(self):
        return self.resolved_content.for_json()

    def commands(self, meta):
        extra_context = (self.resolved_content.resolve(), self.context_name(meta))
        yield Command(("ADD", "{0} {1}".format(self.context_name(meta), self.dest)), extra_context)

class CommandContentAddDict(dictobj):
    fields = {
          "image": "The image to get the content from"
        , "conf": "An Image object for the image"
        , "path": "The path in the image to get the content from"
        , "images": "All images defined by this harpoon configuration"
        , "docker_api": "The docker api"
        }

    def resolve(self):
        return self

    def for_json(self):
        return {"image": self.conf.image_name, "path": self.path}

class CommandAddExtra(dictobj):
    fields = {
          "get": "The files to get"
        , "prefix": "The prefix to add to all the files for their destination in the container"
        }

    def commands(self, meta):
        for val in self.get:
            yield Command(("ADD", self.command_for(val)))

    def command_for(self, val):
        dest = val
        if self.prefix is not NotSpecified:
            dest = "{0}/{1}".format(self.prefix, val)
        return "{0} {1}".format(val, dest)

class CommandCopyExtra(dictobj):
    fields = {
          "from_image": "The image to copy from"
        , "path": "The path in the image to copy from"
        , "to": "The path to copy into"
        , "image": "The original image object"
        }

    def commands(self, meta):
        if type(self.from_image) is int:
            yield Command(("COPY", "--from={0} {1} {2}".format(self.from_image, self.path, self.to)))
        else:
            yield Command(("COPY", "--from={0} {1} {2}".format(self.from_image.from_name, self.path, self.to)), (self, ""))

class complex_from_image_spec(sb.Spec):
    def normalise(self, meta, val):
        from harpoon.option_spec.harpoon_specs import HarpoonSpec
        from harpoon.option_spec.image_objs import Image
        formatted_string = sb.formatted(sb.or_spec(sb.string_spec(), sb.typed(Image)), formatter=MergedOptionStringFormatter)

        img = conf = formatted_string.normalise(meta, val)
        if isinstance(img, six.string_types):
            conf = HarpoonSpec().image_spec.normalise(meta.at("image")
                , { "harpoon": meta.everything["harpoon"]
                  , "commands": ["FROM {0}".format(img)]
                  }
                )
            conf.image_name = img

        return img, conf

class complex_ADD_from_image_spec(sb.Spec):
    def normalise(self, meta, val):
        formatted_string = sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)

        img, conf = complex_from_image_spec().normalise(meta.at("image"), val["image"])
        val["conf"] = conf

        return sb.create_spec(CommandContentAddDict
            , image = sb.overridden(img)
            , conf = sb.any_spec()
            , path = formatted_string
            , images = sb.overridden(meta.everything.get("images", []))
            , docker_api = sb.overridden(meta.everything["harpoon"].docker_api)
            ).normalise(meta, val)

class complex_COPY_spec(sb.Spec):

    def normalise(self, meta, val):
        from harpoon.option_spec.harpoon_specs import HarpoonSpec
        formatted_string = sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)

        if "from" not in val:
            raise BadSpecValue("Specifying [COPY, {options}] must contain 'from' in the options", meta=meta)

        if type(val["from"]) is int:
            val["from_image"] = val["from"]
        else:
            img, conf = complex_from_image_spec().normalise(meta.at("from"), val["from"])
            val["from_image"] = conf
            val["image"] = img

        val = sb.create_spec(CommandCopyExtra
            , from_image = sb.any_spec()
            , path = sb.required(sb.string_spec())
            , to = sb.required(sb.string_spec())
            , image = sb.optional_spec(sb.any_spec())
            ).normalise(meta, val)

        return list(val.commands(meta))

class complex_ADD_spec(sb.Spec):

    def normalise(self, meta, val):
        from harpoon.option_spec.harpoon_specs import HarpoonSpec
        formatted_string = sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)
        val = sb.apply_validators(meta, val, [validators.either_keys(["context"], ["content"], ["get"], ["formatted"])])

        if "get" in val:
            val = sb.create_spec(CommandAddExtra
                , get = sb.required(sb.listof(formatted_string))
                , prefix = sb.optional_spec(sb.string_spec())
                ).normalise(meta, val)

        if "context" in val:
            val = sb.create_spec(CommandContextAdd
                , dest = sb.required(formatted_string)
                , mtime = sb.optional_spec(sb.integer_spec())
                , context = sb.required(HarpoonSpec().context_spec)
                ).normalise(meta, val)

        if "formatted" in val:
            val = sb.create_spec(CommandContentAdd
                , dest = sb.required(formatted_string)
                , mtime = sb.optional_spec(sb.integer_spec())
                , content = sb.overridden(sb.NotSpecified)
                , formatted = sb.container_spec(CommandContentAddString, formatted_string)
                ).normalise(meta, val)

        if "content" in val:
            val = sb.create_spec(CommandContentAdd
                , dest = sb.required(formatted_string)
                , mtime = sb.optional_spec(sb.integer_spec())
                , content = sb.match_spec(
                      (six.string_types, sb.container_spec(CommandContentAddString, sb.string_spec()))
                    , fallback = complex_ADD_from_image_spec()
                    )
                ).normalise(meta, val)

        return list(val.commands(meta))

class array_command_spec(many_item_formatted_spec):
    value_name = "Command"
    specs = [
          # First item is just a string
          sb.string_spec()

          # Second item is a required list of either dicts or strings
        , sb.required( sb.listof( sb.match_spec(
              (dict, sb.dictionary_spec())
            , (six.string_types + (list, ), sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter))
            )))
        ]

    optional_specs = [sb.string_spec()]

    def alter_2(self, action, original_options, options, meta, val):
        result = []
        for o in options:
            if type(o) is dict:
                result.append(convert_dict_command_spec().normalise(meta, {action: o}))
            else:
                result.append(o)
        return result

    def create_result(self, action, command, extra, meta, val, dividers):
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
                    result.append(Command((action, c), extra=extra))

        return result

class convert_dict_command_spec(sb.Spec):
    def normalise(self, meta, val):
        val = sb.dictof(sb.string_spec(), sb.dictionary_spec()).normalise(meta, val)
        if len(val) != 1:
            raise BadSpecValue("Commands specified as [COMMAND, {options}] may only have one option (either ADD or COPY)", got=val, meta=meta)

        items = list(val.items())[0]
        if items[0] not in ("ADD", "COPY"):
            raise BadSpecValue("Commands specified as [COMMAND, {options}] may only have one option (either ADD or COPY)", got=items[0], meta=meta)

        if items[0] == "ADD":
            spec = complex_ADD_spec()
        else:
            spec = complex_COPY_spec()

        result = []

        for val in spec.normalise(meta.at(items[0]), items[1]):
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

# The main spec
# We match against, strings, lists, dictionaries and Command objects with different specs
command_spec = lambda: sb.match_spec(
      (six.string_types, string_command_spec())
    , (list, array_command_spec())
    , (dict, convert_dict_command_spec())
    , (Command, sb.any_spec())
    )
