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

class CommandCase(HarpoonCase):
    def setUp(self):
        self.meta = mock.Mock(name="meta", spec=Meta)

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

describe CommandCase, "Complex ADD spec":
    before_each:
        self.spec = cs.complex_ADD_spec()

    it "complains if dest does not accompany content":
        command = {"content": "blah"}
        with self.fuzzyAssertRaisesError(BadSpecValue, _errors=[BadSpecValue("Expected a value but got none", meta=self.meta.at("dest"))]):
            self.spec.normalise(self.meta, command)

    it "complains if get is not present if no content":
        command = {}
        with self.fuzzyAssertRaisesError(BadSpecValue, _errors=[BadSpecValue("Expected a value but got none", meta=self.meta.at("get"))]):
            self.spec.normalise(self.meta, command)

    it "complains if get is not a string or list":
        for get in (0, 1, None, True, False, {}, {1:2}, type("adf", (object, ), {})(), lambda: 1):
            command = {"get": get}
            actual_error = BadSpecValue("Expected a string", got=type(get), meta=self.meta.at("get").indexed_at(0))
            with self.fuzzyAssertRaisesError(BadSpecValue, _errors=[BadSpecValue(meta=self.meta.at("get"), _errors=[actual_error])]):
                self.spec.normalise(self.meta, command)

    describe "With content":
        it "sets extra context using the content and dest":
            dest = "/somewhere/nice and fun"
            content = "blah de blah blah da"
            command = {"content": content, "dest": dest}

            mtime = mock.Mock(name="mtime")
            everything = {"mtime": lambda ctxt: mtime}
            self.meta.everything = everything

            result = self.spec.normalise(self.meta, command)
            self.assertEqual(result.action, "ADD")
            md5 = hashlib.md5(content.encode('utf-8')).hexdigest()
            self.assertEqual(result.extra_context, (content, "{0}--somewhere-nice--and--fun-mtime({1})".format(md5, mtime)))

        it "sets command as adding in context dest to actual dest":
            dest = "/somewhere/nice and fun"
            content = "blah de blah blah da"
            command = {"content": content, "dest": dest, "mtime": 1430660233}
            result = self.spec.normalise(self.meta, command)
            self.assertDockerLines(command, ["ADD {0} {1}".format(result.extra_context[1], dest)])

    describe "With get":
        it "takes the tedium out of adding multiple files to a destination with the same name":
            command = {"get": ["one", "two", "three"]}
            self.assertDockerLines(command, ["ADD one /one", "ADD two /two", "ADD three /three"])

        it "takes a prefix to add to all the files":
            command = {"get": ["one", "two", "three"], "prefix": "/project"}
            self.assertDockerLines(command, ["ADD one /project/one", "ADD two /project/two", "ADD three /project/three"])

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
        self.meta.indexed_at(0).everything = everything
        self.meta.indexed_at(1).everything = everything

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
        self.meta.indexed_at.assert_called_once_with(0)
        normalise.assert_called_once_with(self.meta.indexed_at(0), second_val)
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
        md5 = hashlib.md5(content.encode('utf-8')).hexdigest()

        everything = MergedOptions.using({"mtime": lambda ctxt: 1430660297, "one": 1, "two": 2, "three": 3, "images": {"blah": blah_image}})
        meta = Meta(everything, [('test', "")])

        commands = [
              ["FROM", "{images.blah}"]
            , "ADD something /somewhere"
            , ["ENV ONE", "{one}"]
            , ["ENV", ["TWO {two}", "THREE {three}"]]
            , ["ADD", {"get": ["blah", "and", "stuff"], "prefix": "/projects"}]
            , {"ADD": {"content": content, "dest": "the_destination"}}
            , {"ADD": {"content": content, "dest": "the_destination2", "mtime": 1530660298}}
            , "CMD cacafire"
            ]

        result = self.spec.normalise(meta, commands)
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
              , "CMD cacafire"
              ]
            )

