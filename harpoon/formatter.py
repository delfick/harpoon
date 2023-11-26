"""
We use this formatter to lookup options in the configuration from strings.

So normally, strings are formatted as follows::

    "blah {0}".format(1) == "blah 1"

What we want is something like this::

    configuration = {"folders": {"root": "/somewhere"}}
    "blah {folders.root}".format() == "blah /somewhere"

To do this we define the MergedOptionStringFormatter below that uses the magic
of MergedOptions to do the lookup for us.
"""

import os

from delfick_project.option_merge.formatter import MergedOptionStringFormatter

from harpoon.errors import NoSuchEnvironmentVariable


class MergedOptionStringFormatter(MergedOptionStringFormatter):
    """
    Resolve format options into a MergedOptions dictionary

    Usage is like:

        configuration = MergedOptions.using({"numbers": "1 two {three}", "three": 3})
        formatter = MergedOptionStringFormatter(configuration, "{numbers}")
        val = formatter.format()
        # val == "1 two 3"

    Where that second argument can be more than one format:

        configuration = MergedOptions.using({"one": 1, "two": 2, "three": 3})
        formatter = MergedOptionStringFormatter(configuration, "{one} {two} {three}")
        val = formatter.format()
        # val == "1 2 3"

    The formatter also has a special feature where it returns the object it finds
    if the string to be formatted is that one object::

        class dictsubclass(dict): pass
        configuration = MergedOptions.using({"some_object": dictsubclass({1:2, 3:4})}, dont_prefix=[dictsubclass])
        formatter = MergedOptionStringFormatter(configuration, "{some_object}")
        val = formatter.format()
        # val == {1:2, 3:4}

    For this to work, the object must be a subclass of dict and in the dont_prefix option of the configuration.
    """

    passthrough_format_specs = ["env", "from_env"]

    def get_string(self, key):
        """Get a string from all_options"""
        # Make sure we special case the "content" option
        if type(key) is str and key.startswith("content."):
            return self.no_format(self.all_options["content"][key[8:]])

        if type(key) is list and len(key) == 2 and key[0] == "content":
            return self.no_format(self.all_options[key])

        return super().get_string(key)

    def special_format_field(self, obj, format_spec):
        """Know about any special formats"""
        if format_spec == "env":
            return "${{{0}}}".format(obj)

        elif format_spec == "from_env":
            if obj not in os.environ:
                raise NoSuchEnvironmentVariable(wanted=obj)
            return os.environ[obj]
