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

    it "uses complex_ADD_spec if the second value is a dictionary with ADD":
        second_val = {self.unique_val(): self.unique_val()}
        normalised = [Command((self.unique_val(), "one")), Command((self.unique_val(), "two")), Command((self.unique_val(), "three"))]
        normalise = mock.Mock(name="normalise", return_value=normalised)

        command = ["ADD", second_val]
        with mock.patch.object(cs.complex_ADD_spec, "normalise", normalise):
            result = self.spec.normalise(self.meta, command)
        self.assertEqual(result, normalised)

    it "uses complex_ADD_spec if the second value is a dictionary with COPY":
        second_val = {self.unique_val(): self.unique_val()}
        normalised = [Command((self.unique_val(), "one")), Command((self.unique_val(), "two")), Command((self.unique_val(), "three"))]
        normalise = mock.Mock(name="normalise", return_value=normalised)

        command = ["COPY", second_val]
        with mock.patch.object(cs.complex_COPY_spec, "normalise", normalise):
            result = self.spec.normalise(self.meta, command)
        self.assertEqual(result, normalised)

describe CommandCase, "convert_dict_command_spec":
    before_each:
        self.spec = cs.convert_dict_command_spec()

    it "uses complex_ADD_spec on the value if the key is ADD":
        val = {self.unique_val(): self.unique_val()}
        command = {"ADD": val}
        normalised = [Command((self.unique_val(), "one")), Command((self.unique_val(), "two")), Command((self.unique_val(), "three"))]
        normalise = mock.Mock(name="normalise", return_value=normalised)

        with mock.patch.object(cs.complex_ADD_spec, "normalise", normalise):
            result = self.spec.normalise(self.meta, command)
        self.assertEqual(result, normalised)

        normalise.assert_called_once_with(self.meta.at("ADD"), val)

    it "uses complex_COPY_spec on the value if the key is COPY":
        val = {self.unique_val(): self.unique_val()}
        command = {"COPY": val}
        normalised = [Command((self.unique_val(), "one")), Command((self.unique_val(), "two")), Command((self.unique_val(), "three"))]
        normalise = mock.Mock(name="normalise", return_value=normalised)

        with mock.patch.object(cs.complex_COPY_spec, "normalise", normalise):
            result = self.spec.normalise(self.meta, command)
        self.assertEqual(result, normalised)

        normalise.assert_called_once_with(self.meta.at("COPY"), val)

    it "complains if the key isn't ADD or COPY":
        error = "Commands specified as \[COMMAND, \{options\}\] may only have one option \(either ADD or COPY\)"
        with self.fuzzyAssertRaisesError(BadSpecValue, error, got="blah", meta=self.meta):
            self.spec.normalise(self.meta, {"blah": {"content": "blah", "dest": "somewhere"}})

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

describe CommandCase, "command_spec":
    before_each:
        self.spec = sb.container_spec(Commands, sb.listof(cs.command_spec()))

    it "works":
        content = self.unique_val()
        blah_image = self.unique_val()
        md5 = hashlib.md5(json.dumps({"content": content}).encode('utf-8')).hexdigest()
        md52 = hashlib.md5(json.dumps({"content": {"image": "blah2", "path": "/tmp/stuff"}}, sort_keys=True).encode("utf-8")).hexdigest()

        blah2_image = mock.Mock(name="blah2", image_name="blah2", from_name="somewhere-blah2")
        blah3_image = mock.Mock(name="blah3", image_name="blah3", from_name="somewhere-blah3")

        everything = MergedOptions.using(
              { "mtime": lambda ctxt: 1430660297, "one": 1, "two": 2, "three": 3, "harpoon": self.harpoon, "config_root": "."
              , "images":
                { "blah2": blah2_image
                , "blah3": blah3_image
                }
              }
            )
        meta = Meta(everything, [])

        commands = [
              ["FROM", blah_image]
            , "ADD something /somewhere"
            , "COPY --from=blah something /somewhere"
            , ["ENV ONE", "{one}"]
            , ["ENV", ["TWO {two}", "THREE {three}"]]
            , ["ADD", {"get": ["blah", "and", "stuff"], "prefix": "/projects"}]
            , {"ADD": {"content": content, "dest": "the_destination"}}
            , {"ADD": {"content": content, "dest": "the_destination2", "mtime": 1530660298}}
            , {"ADD": {"content": {"image": "{images.blah2}", "path": "/tmp/stuff"}, "dest": "the_destination3"}}
            , {"COPY": {"from": "{images.blah2}", "path": "/tmp/stuff", "to": "copy_destination"}}
            , {"COPY": {"from": 1, "path": "/tmp/stuff", "to": "copy_destination"}}
            , ["FROM", "{images.blah3}", "as wat"]
            , "COPY --from=wat things stuff"
            , "CMD cacafire"
            ]

        result = self.spec.normalise(meta.at("images").at("blah").at("commands"), commands)
        self.assertEqual([cmd.as_string for cmd in result.commands]
            , [ "FROM {0}".format(blah_image)
              , "ADD something /somewhere"
              , "COPY --from=blah something /somewhere"
              , "ENV ONE 1"
              , "ENV TWO 2"
              , "ENV THREE 3"
              , "ADD blah /projects/blah"
              , "ADD and /projects/and"
              , "ADD stuff /projects/stuff"
              , "ADD {0}-the_destination-mtime(1430660297) the_destination".format(md5)
              , "ADD {0}-the_destination2-mtime(1530660298) the_destination2".format(md5)
              , "ADD {0}-the_destination3-mtime(1430660297) the_destination3".format(md52)
              , "COPY --from=somewhere-blah2 /tmp/stuff copy_destination"
              , "COPY --from=1 /tmp/stuff copy_destination"
              , "FROM somewhere-blah3 as wat"
              , "COPY --from=wat things stuff"
              , "CMD cacafire"
              ]
            )

        dependents = list(result.dependent_images)
        self.assertEqual(dependents, [blah_image, blah2_image, blah3_image])

        externals = list(result.external_dependencies)
        self.assertEqual(externals, [blah_image])
