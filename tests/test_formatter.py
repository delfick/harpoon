# coding: spec

from harpoon.errors import BadOptionFormat, NoSuchEnvironmentVariable
from harpoon.formatter import MergedOptionStringFormatter

from tests.helpers import HarpoonCase

from input_algorithms.spec_base import NotSpecified
from option_merge import MergedOptions
import uuid
import os

describe HarpoonCase, "MergedOptionStringFormatter":
    def check_formatting(self, configuration, path, value=NotSpecified, expected=NotSpecified, **configuration_kwargs):
        if not isinstance(configuration, MergedOptions):
            configuration = MergedOptions.using(configuration, **configuration_kwargs)

        kwargs = {}
        if value is not NotSpecified:
            kwargs['value'] = value
        formatter = MergedOptionStringFormatter(configuration, path, **kwargs)
        got = formatter.format()

        # Caller must check for exceptions if expected is not specified
        if expected is NotSpecified:
            assert False, "Tester must specify what is expected"
        self.assertEqual(got, expected)

    it "formats from the configuration":
        self.check_formatting({"vars": "one"}, ["vars"], expected="one")

    it "returns as is if formatting to just one value that is a dict":
        class dictsub(dict): pass
        vrs = dictsub({1:2, 3:4})
        self.check_formatting({"vars": vrs}, ["vars"], expected=vrs, dont_prefix=[dictsub])
        self.check_formatting({"vars": vrs}, ["the_vars"], value="{vars}", expected=vrs, dont_prefix=[dictsub])

    it "formats :env as a bash variable":
        self.check_formatting({}, [], value="{blah:env} stuff", expected="${blah} stuff")

    it "formats :from_env as from the environment":
        try:
            value = str(uuid.uuid1())
            assert "WAT_ENV" not in os.environ
            os.environ["WAT_ENV"] = value
            self.check_formatting({}, [], value="{WAT_ENV:from_env} stuff", expected="{0} stuff".format(value))
        finally:
            if "WAT_ENV" in os.environ:
                del os.environ["WAT_ENV"]

    it "complains if from_env references a variable that doesn't exist":
        assert "WAT_ENV" not in os.environ
        with self.fuzzyAssertRaisesError(NoSuchEnvironmentVariable, wanted="WAT_ENV"):
            self.check_formatting({}, [], value="{WAT_ENV:from_env} stuff")

    it "formats formatted values":
        self.check_formatting({"one": "{two}", "two": 2}, [], value="{one}", expected="2")

    it "complains about circular references":
        with self.fuzzyAssertRaisesError(BadOptionFormat, "Recursive option", chain=["two", "one", "two"]):
            self.check_formatting({"one": "{two}", "two": "{one}"}, [], value="{two}", expected="circular reference")

    it "can format into nested dictionaries because MergedOptions is awesome":
        self.check_formatting({"one": {"two": {"three": 4, "five": 5}, "six": 6}}, [], value="{one.two.three}", expected="4")
