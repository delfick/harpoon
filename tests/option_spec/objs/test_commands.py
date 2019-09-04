# coding: spec

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.option_spec import command_specs as cs
from harpoon.option_spec import command_objs as co
from harpoon.errors import HarpoonError

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
from input_algorithms.meta import Meta
import mock
import os

describe HarpoonCase, "Context object":
    it "sets action and command from a space separated string":
        action = self.unique_val()
        cmd = self.unique_val()
        command = co.Command("{0} {1}".format(action, cmd))
        self.assertEqual(command.action, action)
        self.assertEqual(command.command, cmd)

    it "sets action and command from a two item tuple":
        action = self.unique_val()
        cmd = self.unique_val()
        command = co.Command((action, cmd))
        self.assertEqual(command.action, action)
        self.assertEqual(command.command, cmd)

    describe "as_string":
        it "concatenates action and command":
            self.assertEqual(co.Command(("blah", "meh")).as_string, "blah meh")
            self.assertEqual(co.Command("blah meh").as_string, "blah meh")

        it "gets from_name from the command if it's not a string and the action is FROM":
            from_name = self.unique_val()
            cmd = mock.NonCallableMock(name="cmd", from_name=from_name)
            self.assertEqual(co.Command(("FROM", cmd)).as_string, "FROM {0}".format(from_name))

describe HarpoonCase, "Commands":
    before_each:
        self.config_root = self.make_temp_dir()
        self.docker_context = mock.Mock(name="docker_context")
        self.harpoon = HarpoonSpec().harpoon_spec.normalise(
            Meta({}, []), {"docker_context": self.docker_context}
        )
        self.meta = Meta(
            {"harpoon": self.harpoon, "mtime": lambda c: 123, "config_root": self.config_root}, []
        )

    def make_image(self, name, options):
        if "harpoon" not in options:
            options["harpoon"] = self.harpoon
        return HarpoonSpec().image_spec.normalise(self.meta.at("images").at(name), options)

    def make_add_command(self, options):
        return cs.array_command_spec().normalise(self.meta, ["ADD", options])

    def make_copy_command(self, options):
        return cs.array_command_spec().normalise(self.meta, ["COPY", options])

    describe "commands":
        it "goes through all the orig_commands and flattens the commands":
            orig_commands = [
                [co.Command("1 2"), co.Command("3 4")],
                co.Command("5 6"),
                [co.Command("7 8"), co.Command("9 10")],
            ]
            self.assertEqual(
                co.Commands(orig_commands).commands,
                [
                    co.Command("1 2"),
                    co.Command("3 4"),
                    co.Command("5 6"),
                    co.Command("7 8"),
                    co.Command("9 10"),
                ],
            )

    describe "docker_lines":
        it "returns newline seperated as_string of all the commands":
            orig_commands = [
                [co.Command("1 2"), co.Command("3 4")],
                co.Command("5 6"),
                [co.Command("7 8"), co.Command("9 10")],
            ]
            self.assertEqual(co.Commands(orig_commands).docker_lines, "1 2\n3 4\n5 6\n7 8\n9 10")

    describe "docker_lines_list":
        it "returns list of as_string of all the commands":
            orig_commands = [
                [co.Command("1 2"), co.Command("3 4")],
                co.Command("5 6"),
                [co.Command("7 8"), co.Command("9 10")],
            ]
            self.assertEqual(
                co.Commands(orig_commands).docker_lines_list, ["1 2", "3 4", "5 6", "7 8", "9 10"]
            )

    describe "extra_context":
        it "yields all the extra_context found on commands":
            ec1 = mock.Mock(name="ec1")
            ec2 = mock.Mock(name="ec2")
            orig_commands = [
                [co.Command("1 2", ec1), co.Command("3 4")],
                co.Command("5 6", ec2),
                [co.Command("7 8"), co.Command("9 10")],
            ]
            self.assertEqual(list(co.Commands(orig_commands).extra_context), [ec1, ec2])

    describe "dependent_images":
        it "yields the first FROM if that's the only dep":
            orig_commands = [co.Command("FROM blah:12"), co.Command("3 4"), co.Command("5 6")]
            self.assertEqual(list(co.Commands(orig_commands).dependent_images), ["blah:12"])

        it "yields if FROM is from another image in the confguration":
            image = mock.Mock(name="image")
            orig_commands = [co.Command(("FROM", image)), co.Command("3 4"), co.Command("5 6")]
            self.assertEqual(list(co.Commands(orig_commands).dependent_images), [image])

        it "yields if we have staged FROMs":
            image = mock.Mock(name="image")
            orig_commands = [co.Command(("FROM", image)), co.Command("3 4"), co.Command("5 6")]
            self.assertEqual(list(co.Commands(orig_commands).dependent_images), [image])

        it "yields all if there are many FROMS":
            image = mock.Mock(name="image")
            orig_commands = [
                co.Command(("FROM", image), extra="as wat"),
                co.Command("3 4"),
                co.Command("5 6"),
                co.Command("FROM meh:14 as stuff"),
                co.Command("3 4"),
                co.Command("5 6"),
                co.Command("FROM another"),
                co.Command("3 4"),
                co.Command("5 6"),
            ]
            self.assertEqual(
                list(co.Commands(orig_commands).dependent_images), [image, "meh:14", "another"]
            )

        it "yields from ADDs that have images":
            harpoon = mock.Mock(name="harpoon")
            image = self.make_image("image1", {"commands": ["FROM elsewhere"]})
            image2 = self.make_image("image2", {"commands": ["FROM elsewhere"]})

            add1 = self.make_add_command(
                {"dest": "/", "content": {"image": "thing:latest", "path": "/thing"}}
            )
            add2 = self.make_add_command(
                {"dest": "/", "content": {"image": image2, "path": "/thing"}}
            )
            add3 = self.make_add_command({"dest": "/", "content": "blah"})

            orig_commands = [
                co.Command(("FROM", image)),
                co.Command("3 4"),
                co.Command("5 6"),
                add1,
                co.Command("FROM meh:14"),
                co.Command("3 4"),
                co.Command("5 6"),
                add2,
                add3,
            ]
            self.assertEqual(
                list(co.Commands(orig_commands).dependent_images),
                [image, "thing:latest", "meh:14", image2],
            )

        it "yields from COPYs that have images":
            harpoon = mock.Mock(name="harpoon")
            image = self.make_image("image1", {"commands": ["FROM elsewhere"]})
            image2 = self.make_image("image2", {"commands": ["FROM elsewhere"]})

            copy1 = self.make_copy_command({"from": "thing:latest", "to": "/", "path": "/thing"})
            copy2 = self.make_copy_command({"from": image2, "to": "/", "path": "/thing"})

            orig_commands = [
                co.Command(("FROM", image)),
                co.Command("3 4"),
                co.Command("5 6"),
                copy1,
                co.Command("FROM meh:14"),
                co.Command("3 4"),
                co.Command("5 6"),
                copy2,
            ]
            self.assertEqual(
                list(co.Commands(orig_commands).dependent_images),
                [image, "thing:latest", "meh:14", image2],
            )

    describe "external_dependencies":
        it "returns the string deps from dependent_images":
            harpoon = mock.Mock(name="harpoon")
            image = self.make_image("image1", {"commands": ["FROM elsewhere"]})
            image2 = self.make_image("image2", {"commands": ["FROM elsewhere"]})

            add1 = self.make_add_command(
                {"dest": "/", "content": {"image": "thing:latest", "path": "/thing"}}
            )
            add2 = self.make_add_command(
                {"dest": "/", "content": {"image": image2, "path": "/thing"}}
            )
            add3 = self.make_add_command({"dest": "/", "content": "blah"})

            orig_commands = [
                co.Command(("FROM", image)),
                co.Command("3 4"),
                co.Command("5 6"),
                add1,
                co.Command("FROM meh:14"),
                co.Command("3 4"),
                co.Command("5 6"),
                add2,
                add3,
            ]
            self.assertEqual(
                list(co.Commands(orig_commands).external_dependencies), ["thing:latest", "meh:14"]
            )
