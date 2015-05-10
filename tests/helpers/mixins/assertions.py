from harpoon.errors import HarpoonError

from contextlib import contextmanager
from textwrap import dedent
import json
import six
import re

class NotSpecified(object):
    """Tell the difference between empty and None"""

class AssertionsAssertionsMixin:
    def assertSortedEqual(self, one, two):
        """Assert that the sorted of the two equal"""
        self.assertEqual(sorted(one), sorted(two))

    def assertJsonDictEqual(self, one, two):
        """Assert the two dictionaries are the same, print out as json if not"""
        try:
            self.assertEqual(one, two)
        except AssertionError:
            print("Got =============>")
            print(json.dumps(one, indent=2, sort_keys=True))
            print("Expected --------------->")
            print(json.dumps(two, indent=2, sort_keys=True))
            raise

    def assertReMatchLines(self, expected, output):
        """Assert that all the lines match each other in order"""
        expected = dedent(expected).strip()
        expected_lines = expected.split('\n')
        expected = expected.encode('utf-8')

        output = dedent(output).strip()
        output_lines = output.split('\n')
        output = output.encode('utf-8')

        if len(expected_lines) != len(output_lines):
            assert False, "Expected ===>\n{0}\n\nTo match ===>\n{1}".format(expected, output)

        for a, b in zip(expected_lines, output_lines):
            if not isinstance(a, six.binary_type):
                a = a.encode('utf-8')
            if not isinstance(b, six.binary_type):
                b = b.encode('utf-8')
            assert re.match(a, b), "expected ===>\n{0}\n\nTo match ===>\n{1}\n\n===>Failed matching {2} to {3}".format(expected, output, a, b)

    @contextmanager
    def fuzzyAssertRaisesError(self, expected_kls, expected_msg_regex=NotSpecified, **values):
        """
        Assert that something raises a particular type of error.

        The error raised must be a subclass of the expected_kls
        Have a message that matches the specified regex.

        And have atleast the values specified in it's kwargs.
        """
        try:
            yield
        except HarpoonError as error:
            try:
                assert issubclass(error.__class__, expected_kls)
                if expected_msg_regex is not NotSpecified:
                    self.assertRegexpMatches(expected_msg_regex, error.message)

                errors = values.get("_errors")
                if "_errors" in values:
                    del values["_errors"]

                self.assertDictContainsSubset(values, error.kwargs)
                if errors:
                    self.assertEqual(sorted(error.errors), sorted(errors))
            except AssertionError:
                print("Got error: {0}".format(error))
                print("Expected: {0}: {1}: {2}".format(expected_kls, expected_msg_regex, values))
                raise
        else:
            assert False, "Expected an exception to be raised\n\texpected_kls: {0}\n\texpected_msg_regex: {1}\n\thave_atleast: {2}".format(
                expected_kls, expected_msg_regex, values
            )

