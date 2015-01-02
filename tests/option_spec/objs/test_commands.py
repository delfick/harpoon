# coding: spec

from harpoon.option_spec import command_objs as co
from harpoon.errors import HarpoonError

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
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

        it "gets image_name from the command if it's not a string and the action is FROM":
            image_name = self.unique_val()
            cmd = mock.NonCallableMock(name="cmd", image_name=image_name)
            self.assertEqual(co.Command(("FROM", cmd)).as_string, "FROM {0}".format(image_name))

describe HarpoonCase, "Commands":
    describe "commands":
        it "goes through all the orig_commands and flattens the commands":
            orig_commands = [[co.Command("1 2"), co.Command("3 4")], co.Command("5 6"), [co.Command("7 8"), co.Command("9 10")]]
            self.assertEqual(co.Commands(orig_commands).commands, [co.Command("1 2"), co.Command("3 4"), co.Command("5 6"), co.Command("7 8"), co.Command("9 10")])

    describe "parent_image":
        it "returns the command from the FROM command":
            commands = [co.Command("AUTHOR joe.smith"), co.Command("MAINTAINER jimmy"), co.Command("FROM somewhere"), co.Command("CMD cacafire")]
            self.assertEqual(co.Commands(commands).parent_image, "somewhere")

    describe "parent_image_name":
        it "returns the parent_image as is if it's a string":
            commands = [co.Command("FROM somewhere")]
            self.assertEqual(co.Commands(commands).parent_image_name, "somewhere")

        it "returns the image_name of the command if it's not a string":
            name = self.unique_val()
            container = mock.NonCallableMock(name="container", image_name=name)
            self.assertEqual(co.Commands([co.Command(("FROM", container))]).parent_image_name, name)

    describe "docker_lines":
        it "returns newline seperated as_string of all the commands":
            orig_commands = [[co.Command("1 2"), co.Command("3 4")], co.Command("5 6"), [co.Command("7 8"), co.Command("9 10")]]
            self.assertEqual(co.Commands(orig_commands).docker_lines, "1 2\n3 4\n5 6\n7 8\n9 10")

    describe "extra_context":
        it "yields all the extra_context found on commands":
            ec1 = mock.Mock(name="ec1")
            ec2 = mock.Mock(name="ec2")
            orig_commands = [[co.Command("1 2", ec1), co.Command("3 4")], co.Command("5 6", ec2), [co.Command("7 8"), co.Command("9 10")]]
            self.assertEqual(list(co.Commands(orig_commands).extra_context), [ec1, ec2])

