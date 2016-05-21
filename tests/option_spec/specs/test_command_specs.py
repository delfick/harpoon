# coding: spec

from harpoon.option_spec.command_objs import Command, Commands
from harpoon.option_spec import command_specs as cs
from harpoon.errors import BadSpecValue, BadOption

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
from input_algorithms import spec_base as sb
from input_algorithms.meta import Meta
from option_merge import MergedOptions
import hashlib
import mock
import json

class CommandCase(HarpoonCase):
    def setUp(self):
        self.docker_context = mock.Mock(name="docker_context")
        self.harpoon = mock.Mock(name="harpoon", docker_context=self.docker_context)
        self.meta = Meta({"config_root": '.', "harpoon": self.harpoon}, [])

    def assertDockerLines(self, command, expected):
        """
        Given a spec and a command

        Normalise the spec with the command and compare the as_string of the resulting
        commands with the expected
        """
        result = self.spec.normalise(self.meta, command)
        if isinstance(result, Command):
            result = [result]
        self.assertEqual([cmd.as_string for cmd in result], expected)

describe CommandCase, "array_command_spec":
    before_each:
        self.spec = cs.array_command_spec()

    it "complains if it's a one item value":
        command = ["ENV 1"]
        with self.fuzzyAssertRaisesError(BadSpecValue, "The value is a list with the wrong number of items", meta=self.meta):
            self.spec.normalise(self.meta, command)

    it "returns multiple commands if second value is an array":
        command = ["ENV", ["ONE", "TWO", "THREE"]]
        self.assertDockerLines(command, ["ENV ONE", "ENV TWO", "ENV THREE"])

    it "formats second list":
        everything = MergedOptions.using({"one": 1, "two": 2})
        self.meta.everything = everything

        command = ["ENV", "ONE {one}"]
        self.assertDockerLines(command, ["ENV ONE 1"])

        command = ["ENV", ["ONE {one}", "TWO {two}"]]
        self.assertDockerLines(command, ["ENV ONE 1", "ENV TWO 2"])

    it "uses complex_ADD_spec if the second value is a dictionary":
        second_val = {self.unique_val(): self.unique_val()}
        normalised = [Command((self.unique_val(), "one")), Command((self.unique_val(), "two")), Command((self.unique_val(), "three"))]
        normalise = mock.Mock(name="normalise", return_value=normalised)

        command = [self.unique_val(), second_val]
        with mock.patch.object(cs.complex_ADD_spec, "normalise", normalise):
            result = self.spec.normalise(self.meta, command)
        self.assertEqual(result, normalised)

describe CommandCase, "convert_dict_command_spec":
    it "returns the flattened values from normalising it's spec":
        val1 = self.unique_val()
        val2 = self.unique_val()
        normalised = {self.unique_val(): [val1], self.unique_val(): [val2]}

        class spec(object):
            def normalise(slf, meta, val):
                return normalised

        result = cs.convert_dict_command_spec(spec()).normalise(self.meta, self.unique_val())
        self.assertEqual(sorted(result), sorted([val1, val2]))

describe CommandCase, "has_a_space validator":
    it "complains if there is no space in the value":
        val = self.unique_val()
        with self.fuzzyAssertRaisesError(BadOption, "Expected string to have a space .+", meta=self.meta, got=val):
            cs.has_a_space().normalise(self.meta, val)

    it "just returns the value if it has a space":
        val = "{0} {1}".format(self.unique_val(), self.unique_val())
        self.assertEqual(cs.has_a_space().normalise(self.meta, val), val)

    it "just returns the value if it has multiple spaces":
        val = "{0} {1} {2}".format(self.unique_val(), self.unique_val(), self.unique_val())
        self.assertEqual(cs.has_a_space().normalise(self.meta, val), val)

describe CommandCase, "string_command_spec":
    before_each:
        self.spec = cs.string_command_spec()

    it "complains if given a string without a space":
        val = self.unique_val()
        with self.fuzzyAssertRaisesError(BadOption, "Expected string to have a space .+", meta=self.meta, got=val):
            cs.string_command_spec().normalise(self.meta, val)

    it "returns a Command object without formatting":
        self.meta.everything = MergedOptions.using({"thing": self.unique_val()})
        val = "FROM {thing}"
        result = cs.string_command_spec().normalise(self.meta, val)
        self.assertEqual(result.action, "FROM")
        self.assertEqual(result.command, "{thing}")
        self.assertDockerLines(val, ["FROM {thing}"])

describe CommandCase, "dictionary_command_spec":
    before_each:
        self.spec = cs.dictionary_command_spec()

    it "uses complex_ADD_spec on the value":
        val = self.unique_val()
        command = {"ADD": val}
        normalised = [Command((self.unique_val(), "one")), Command((self.unique_val(), "two")), Command((self.unique_val(), "three"))]
        normalise = mock.Mock(name="normalise", return_value=normalised)

        with mock.patch.object(cs.complex_ADD_spec, "normalise", normalise):
            result = self.spec.normalise(self.meta, command)
        self.assertEqual(result, normalised)

        normalise.assert_called_once_with(self.meta.at("ADD"), val)

    it "complains if the key isn't ADD":
        actual_error = BadSpecValue("Expected the value to be one of the valid choices", choices=("ADD", ), got="blah", meta=self.meta.at("blah"))
        with self.fuzzyAssertRaisesError(BadSpecValue, meta=self.meta, _errors=[BadSpecValue("Failed to validate", meta=self.meta.at("blah"), _errors=[actual_error])]):
            self.spec.normalise(self.meta, {"blah": {"content": "blah", "dest": "somewhere"}})

describe CommandCase, "command_spec":
    before_each:
        self.spec = sb.container_spec(Commands, sb.listof(cs.command_spec()))

    it "works":
        content = self.unique_val()
        blah_image = self.unique_val()
        md5 = hashlib.md5(json.dumps({"content": content}).encode('utf-8')).hexdigest()
        md52 = hashlib.md5(json.dumps({"content": {"image": "blah2", "path": "/tmp/stuff"}}, sort_keys=True).encode("utf-8")).hexdigest()

        everything = MergedOptions.using(
              { "mtime": lambda ctxt: 1430660297, "one": 1, "two": 2, "three": 3, "harpoon": self.harpoon, "config_root": "."
              , "images":
                { "blah": blah_image
                , "blah2": mock.Mock(name="blah2", image_name="blah2")
                }
              }
            )
        meta = Meta(everything, [])

        commands = [
              ["FROM", "{images.blah}"]
            , "ADD something /somewhere"
            , ["ENV ONE", "{one}"]
            , ["ENV", ["TWO {two}", "THREE {three}"]]
            , ["ADD", {"get": ["blah", "and", "stuff"], "prefix": "/projects"}]
            , {"ADD": {"content": content, "dest": "the_destination"}}
            , {"ADD": {"content": content, "dest": "the_destination2", "mtime": 1530660298}}
            , {"ADD": {"content": {"image": "{images.blah2}", "path": "/tmp/stuff"}, "dest": "the_destination3"}}
            , "CMD cacafire"
            ]

        result = self.spec.normalise(meta.at("images").at("blah").at("commands"), commands)
        self.assertEqual([cmd.as_string for cmd in result.commands]
            , [ "FROM {0}".format(blah_image)
              , "ADD something /somewhere"
              , "ENV ONE 1"
              , "ENV TWO 2"
              , "ENV THREE 3"
              , "ADD blah /projects/blah"
              , "ADD and /projects/and"
              , "ADD stuff /projects/stuff"
              , "ADD {0}-the_destination-mtime(1430660297) the_destination".format(md5)
              , "ADD {0}-the_destination2-mtime(1530660298) the_destination2".format(md5)
              , "ADD {0}-the_destination3-mtime(1430660297) the_destination3".format(md52)
              , "CMD cacafire"
              ]
            )

