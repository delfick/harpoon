# coding: spec

from harpoon.option_spec.command_objs import Command, Commands
from harpoon.option_spec import command_specs as cs
from harpoon.errors import BadSpecValue, BadOption

from tests.helpers import CommandCase

from delfick_project.option_merge import MergedOptions
from delfick_project.errors_pytest import assertRaises
from delfick_project.norms import sb, Meta
from unittest import mock
import hashlib
import pytest
import json


describe CommandCase, "array_command_spec":

    @pytest.fixture()
    def spec(self):
        return cs.array_command_spec()

    it "complains if it's a one item value", spec, meta:
        command = ["ENV 1"]
        with assertRaises(
            BadSpecValue, "The value is a list with the wrong number of items", meta=meta
        ):
            spec.normalise(meta, command)

    it "returns multiple commands if second value is an array", spec, meta, assertDockerLines:
        command = ["ENV", ["ONE", "TWO", "THREE"]]
        assertDockerLines(command, ["ENV ONE", "ENV TWO", "ENV THREE"])

    it "formats second list", meta, assertDockerLines:
        everything = MergedOptions.using({"one": 1, "two": 2})
        meta.everything = everything

        command = ["ENV", "ONE {one}"]
        assertDockerLines(command, ["ENV ONE 1"])

        command = ["ENV", ["ONE {one}", "TWO {two}"]]
        assertDockerLines(command, ["ENV ONE 1", "ENV TWO 2"])

    it "uses complex_ADD_spec if the second value is a dictionary with ADD", spec, meta:
        second_val = {self.unique_val(): self.unique_val()}
        normalised = [
            Command((self.unique_val(), "one")),
            Command((self.unique_val(), "two")),
            Command((self.unique_val(), "three")),
        ]
        normalise = mock.Mock(name="normalise", return_value=normalised)

        command = ["ADD", second_val]
        with mock.patch.object(cs.complex_ADD_spec, "normalise", normalise):
            result = spec.normalise(meta, command)
        assert result == normalised

    it "uses complex_ADD_spec if the second value is a dictionary with COPY", spec, meta:
        second_val = {self.unique_val(): self.unique_val()}
        normalised = [
            Command((self.unique_val(), "one")),
            Command((self.unique_val(), "two")),
            Command((self.unique_val(), "three")),
        ]
        normalise = mock.Mock(name="normalise", return_value=normalised)

        command = ["COPY", second_val]
        with mock.patch.object(cs.complex_COPY_spec, "normalise", normalise):
            result = spec.normalise(meta, command)
        assert result == normalised

describe CommandCase, "convert_dict_command_spec":

    @pytest.fixture()
    def spec(self):
        return cs.convert_dict_command_spec()

    it "uses complex_ADD_spec on the value if the key is ADD", spec, meta:
        val = {self.unique_val(): self.unique_val()}
        command = {"ADD": val}
        normalised = [
            Command((self.unique_val(), "one")),
            Command((self.unique_val(), "two")),
            Command((self.unique_val(), "three")),
        ]
        normalise = mock.Mock(name="normalise", return_value=normalised)

        with mock.patch.object(cs.complex_ADD_spec, "normalise", normalise):
            result = spec.normalise(meta, command)
        assert result == normalised

        normalise.assert_called_once_with(meta.at("ADD"), val)

    it "uses complex_COPY_spec on the value if the key is COPY", spec, meta:
        val = {self.unique_val(): self.unique_val()}
        command = {"COPY": val}
        normalised = [
            Command((self.unique_val(), "one")),
            Command((self.unique_val(), "two")),
            Command((self.unique_val(), "three")),
        ]
        normalise = mock.Mock(name="normalise", return_value=normalised)

        with mock.patch.object(cs.complex_COPY_spec, "normalise", normalise):
            result = spec.normalise(meta, command)
        assert result == normalised

        normalise.assert_called_once_with(meta.at("COPY"), val)

    it "complains if the key isn't ADD or COPY", spec, meta:
        error = r"Commands specified as \[COMMAND, \{options\}\] may only have one option \(either ADD or COPY\)"
        with assertRaises(BadSpecValue, error, got="blah", meta=meta):
            spec.normalise(meta, {"blah": {"content": "blah", "dest": "somewhere"}})

describe CommandCase, "has_a_space validator":
    it "complains if there is no space in the value", meta:
        val = self.unique_val()
        with assertRaises(BadOption, "Expected string to have a space .+", meta=meta, got=val):
            cs.has_a_space().normalise(meta, val)

    it "just returns the value if it has a space", meta:
        val = "{0} {1}".format(self.unique_val(), self.unique_val())
        assert cs.has_a_space().normalise(meta, val) == val

    it "just returns the value if it has multiple spaces", meta:
        val = "{0} {1} {2}".format(self.unique_val(), self.unique_val(), self.unique_val())
        assert cs.has_a_space().normalise(meta, val) == val

describe CommandCase, "string_command_spec":

    @pytest.fixture()
    def spec(self):
        return cs.string_command_spec()

    it "complains if given a string without a space", meta:
        val = self.unique_val()
        with assertRaises(BadOption, "Expected string to have a space .+", meta=meta, got=val):
            cs.string_command_spec().normalise(meta, val)

    it "returns a Command object without formatting", meta, assertDockerLines:
        meta.everything = MergedOptions.using({"thing": self.unique_val()})
        val = "FROM {thing}"
        result = cs.string_command_spec().normalise(meta, val)
        assert result.action == "FROM"
        assert result.command == "{thing}"
        assertDockerLines(val, ["FROM {thing}"])

describe CommandCase, "command_spec":

    @pytest.fixture()
    def spec(self):
        return sb.container_spec(Commands, sb.listof(cs.command_spec()))

    it "works", meta, spec:
        content = self.unique_val()
        blah_image = self.unique_val()
        md5 = hashlib.md5(json.dumps({"content": content}).encode("utf-8")).hexdigest()
        md52 = hashlib.md5(
            json.dumps(
                {"content": {"image": "blah2", "path": "/tmp/stuff"}}, sort_keys=True
            ).encode("utf-8")
        ).hexdigest()

        blah2_image = mock.Mock(name="blah2", image_name="blah2", from_name="somewhere-blah2")
        blah3_image = mock.Mock(name="blah3", image_name="blah3", from_name="somewhere-blah3")

        everything = MergedOptions.using(
            {
                "one": 1,
                "two": 2,
                "three": 3,
                "harpoon": meta.everything["harpoon"],
                "config_root": ".",
                "images": {"blah2": blah2_image, "blah3": blah3_image},
            }
        )
        meta = Meta(everything, [])

        commands = [
            "FROM somewhere as base",
            ["FROM", blah_image],
            "ADD something /somewhere",
            "COPY --from=blah something /somewhere",
            ["ENV ONE", "{one}"],
            ["ENV", ["TWO {two}", "THREE {three}"]],
            ["ADD", {"get": ["blah", "and", "stuff"], "prefix": "/projects"}],
            {"ADD": {"content": content, "dest": "the_destination"}},
            {"ADD": {"content": content, "dest": "the_destination2"}},
            {
                "ADD": {
                    "content": {"image": "{images.blah2}", "path": "/tmp/stuff"},
                    "dest": "the_destination3",
                }
            },
            {"COPY": {"from": "{images.blah2}", "path": "/tmp/stuff", "to": "copy_destination"}},
            {"COPY": {"from": 1, "path": "/tmp/stuff", "to": "copy_destination"}},
            ["FROM", "{images.blah3}", "as wat"],
            "COPY --from=wat things stuff",
            "CMD cacafire",
        ]

        result = spec.normalise(meta.at("images").at("blah").at("commands"), commands)
        assert [cmd.as_string for cmd in result.commands] == [
            "FROM somewhere as base",
            "FROM {0}".format(blah_image),
            "ADD something /somewhere",
            "COPY --from=blah something /somewhere",
            "ENV ONE 1",
            "ENV TWO 2",
            "ENV THREE 3",
            "ADD blah /projects/blah",
            "ADD and /projects/and",
            "ADD stuff /projects/stuff",
            "ADD {0}-the_destination the_destination".format(md5),
            "ADD {0}-the_destination2 the_destination2".format(md5),
            "ADD {0}-the_destination3 the_destination3".format(md52),
            "COPY --from=somewhere-blah2 /tmp/stuff copy_destination",
            "COPY --from=1 /tmp/stuff copy_destination",
            "FROM somewhere-blah3 as wat",
            "COPY --from=wat things stuff",
            "CMD cacafire",
        ]

        dependents = list(result.dependent_images)
        assert dependents == ["somewhere", blah_image, blah2_image, blah3_image]

        externals = list(result.external_dependencies)
        assert externals == ["somewhere", blah_image]
