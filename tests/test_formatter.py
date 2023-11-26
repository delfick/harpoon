# coding: spec

import os
import uuid

from delfick_project.errors_pytest import assertRaises
from delfick_project.norms import sb
from delfick_project.option_merge import MergedOptions

from harpoon.errors import BadOptionFormat, NoSuchEnvironmentVariable
from harpoon.formatter import MergedOptionStringFormatter
from tests.helpers import HarpoonCase

describe HarpoonCase, "MergedOptionStringFormatter":

    def check_formatting(
        self, configuration, value, expected=sb.NotSpecified, **configuration_kwargs
    ):
        if not isinstance(configuration, MergedOptions):
            configuration = MergedOptions.using(configuration, **configuration_kwargs)

        formatter = MergedOptionStringFormatter(configuration, value)
        got = formatter.format()

        # Caller must check for exceptions if expected is not specified
        if expected is sb.NotSpecified:
            assert False, "Tester must specify what is expected"
        assert got == expected

    it "formats from the configuration":
        self.check_formatting({"vars": "one"}, "{vars}", expected="one")

    it "returns as is if formatting to just one value that is a dict":

        class dictsub(dict):
            pass

        vrs = dictsub({1: 2, 3: 4})
        self.check_formatting({"vars": vrs}, "{vars}", expected=vrs, dont_prefix=[dictsub])

    it "formats :env as a bash variable":
        self.check_formatting({}, "{blah:env} stuff", expected="${blah} stuff")

    it "formats :from_env as from the environment":
        try:
            value = str(uuid.uuid1())
            assert "WAT_ENV" not in os.environ
            os.environ["WAT_ENV"] = value
            self.check_formatting(
                {}, "{WAT_ENV:from_env} stuff", expected="{0} stuff".format(value)
            )
        finally:
            if "WAT_ENV" in os.environ:
                del os.environ["WAT_ENV"]

    it "complains if from_env references a variable that doesn't exist":
        assert "WAT_ENV" not in os.environ
        with assertRaises(NoSuchEnvironmentVariable, wanted="WAT_ENV"):
            self.check_formatting({}, "{WAT_ENV:from_env} stuff")

    it "formats formatted values":
        self.check_formatting({"one": "{two}", "two": 2}, "{one}", expected="2")

    it "complains about circular references":
        with assertRaises(BadOptionFormat, "Recursive option", chain=["two", "one", "two"]):
            self.check_formatting(
                {"one": "{two}", "two": "{one}"}, "{two}", expected="circular reference"
            )

    it "can format into nested dictionaries because MergedOptions is awesome":
        self.check_formatting(
            {"one": {"two": {"three": 4, "five": 5}, "six": 6}}, "{one.two.three}", expected="4"
        )
