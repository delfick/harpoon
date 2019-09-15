"""
    Create a base class that includes all the mixins in the mixins folder
"""
from delfick_project.errors import DelfickErrorTestMixin
import pkg_resources
import unittest
import os

this_dir = os.path.dirname(__file__)
mixin_dir = os.path.join(this_dir, "mixins")
harpoon_dir = os.path.abspath(pkg_resources.resource_filename("harpoon", ""))

bases = [unittest.TestCase, DelfickErrorTestMixin]
for name in os.listdir(mixin_dir):
    if not name or name.startswith("_") or not name.endswith(".py"):
        continue

    # Name convention is <Name>AssertionsMixin
    name = name[:-3]
    mixin = "%sAssertionsMixin" % name.capitalize()
    imported = __import__("mixins.{0}".format(name), globals(), locals(), [mixin], 1)
    bases.append(getattr(imported, mixin))


def harpoon_case_teardown(self):
    """Run any registered teardown function"""
    for tearer in self._teardowns:
        tearer()


def harpoon_init(self, methodName="runTest"):
    """
    We need to do some trickery with runTest so that it all works.

    Also add any function with the attribute "_harpoon_case_teardown" to self._teardowns
    """
    self._teardowns = []
    for attr in dir(self):
        if attr != "docker_client":
            thing = getattr(self, attr)
            if hasattr(thing, "_harpoon_case_teardown"):
                self._teardowns.append(thing)

    if methodName == "runTest":
        methodName = "empty"
    return unittest.TestCase.__init__(self, methodName)


# Empty function that does nothing
empty_func = lambda self: False

HarpoonCase = type(
    "HarpoonCase",
    tuple(bases),
    {
        "empty": empty_func,
        "__init__": harpoon_init,
        "tearDown": harpoon_case_teardown,
        "teardown": harpoon_case_teardown,
        "harpoon_dir": harpoon_dir,
    },
)
