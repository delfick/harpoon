"""
    Create a base class that includes all the mixins in the mixins folder
"""
import os
from unittest import mock

import pkg_resources
import pytest
from delfick_project.norms import Meta

from harpoon.option_spec.command_objs import Command

this_dir = os.path.dirname(__file__)
mixin_dir = os.path.join(this_dir, "mixins")
harpoon_dir = os.path.abspath(pkg_resources.resource_filename("harpoon", ""))

bases = []
for name in os.listdir(mixin_dir):
    if not name or name.startswith("_") or not name.endswith(".py"):
        continue

    # Name convention is <Name>AssertionsMixin
    name = name[:-3]
    mixin = "%sAssertionsMixin" % name.capitalize()
    imported = __import__("mixins.{0}".format(name), globals(), locals(), [mixin], 1)
    bases.append(getattr(imported, mixin))


@pytest.fixture(autouse=True)
def harpoon_case_teardown(self):
    """Run any registered teardown function"""
    try:
        yield
    finally:
        for attr in dir(self):
            if attr != "docker_client":
                thing = getattr(self, attr)
                if hasattr(thing, "_harpoon_case_teardown"):
                    thing()


# Empty function that does nothing
empty_func = lambda self: False

HarpoonCase = type(
    "HarpoonCase",
    tuple(bases),
    {
        "empty": empty_func,
        "harpoon_case_teardown": harpoon_case_teardown,
        "harpoon_dir": harpoon_dir,
    },
)


class CommandCase(HarpoonCase):
    @pytest.fixture()
    def meta(self):
        docker_context = mock.Mock(name="docker_context")
        harpoon = mock.Mock(name="harpoon", docker_context=docker_context)
        return Meta({"config_root": ".", "harpoon": harpoon}, [])

    @pytest.fixture()
    def assertDockerLines(self, meta, spec):
        def assertDockerLines(command, expected):
            """
            Given a spec and a command

            Normalise the spec with the command and compare the as_string of the resulting
            commands with the expected
            """
            result = spec.normalise(meta, command)
            if isinstance(result, Command):
                result = [result]
            assert [cmd.as_string for cmd in result] == expected

        return assertDockerLines
