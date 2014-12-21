# coding: spec

from harpoon.formatter import MergedOptionStringFormatter
from harpoon.errors import BadOptionFormat

from tests.helpers import HarpoonCase

from input_algorithms.spec_base import NotSpecified
from option_merge import MergedOptions

describe HarpoonCase, "MergedOptionStringFormatter":
    def check_formatting(self, configuration, path, value=NotSpecified, expected=NotSpecified, **configuration_kwargs):
        if expected is NotSpecified:
            assert False, "Tester must specify what is expected"

        if not isinstance(configuration, MergedOptions):
            configuration = MergedOptions.using(configuration, **configuration_kwargs)

        kwargs = {}
        if value is not NotSpecified:
            kwargs['value'] = value
        formatter = MergedOptionStringFormatter(configuration, path, **kwargs)
        self.assertEqual(formatter.format(), expected)

    it "formats from the configuration":
        self.check_formatting({"vars": "one"}, ["vars"], expected="one")

    it "returns as is if formatting to just one value that is a dict":
        class dictsub(dict): pass
        vrs = dictsub({1:2, 3:4})
        self.check_formatting({"vars": vrs}, ["vars"], expected=vrs, dont_prefix=[dictsub])
        self.check_formatting({"vars": vrs}, ["the_vars"], value="{vars}", expected=vrs, dont_prefix=[dictsub])

    it "formats :env as a bash variable":
        self.check_formatting({}, [], value="{blah:env} stuff", expected="${blah} stuff")

    it "formats formatted values":
        self.check_formatting({"one": "{two}", "two": 2}, [], value="{one}", expected="2")

    it "complains about circular references":
        with self.fuzzyAssertRaisesError(BadOptionFormat, "Recursive option", chain=["two", "one", "two"]):
            self.check_formatting({"one": "{two}", "two": "{one}"}, [], value="{two}", expected="circular reference")

    it "can format into nested dictionaries because MergedOptions is awesome":
        self.check_formatting({"one": {"two": {"three": 4, "five": 5}, "six": 6}}, [], value="{one.two.three}", expected="4")

