from textwrap import dedent
import json
import re


class NotSpecified(object):
    """Tell the difference between empty and None"""


class AssertionsAssertionsMixin:
    def assertSortedEqual(self, one, two):
        """Assert that the sorted of the two equal"""
        assert sorted(one) == sorted(two)

    def assertJsonDictEqual(self, one, two):
        """Assert the two dictionaries are the same, print out as json if not"""
        try:
            assert one == two
        except AssertionError:
            print("Got =============>")
            print(json.dumps(one, indent=2, sort_keys=True))
            print("Expected --------------->")
            print(json.dumps(two, indent=2, sort_keys=True))
            raise

    def assertReMatchLines(self, expected, output, remove=None):
        """Assert that all the lines match each other in order"""
        expected = dedent(expected).strip()
        expected_lines = expected.split("\n")
        expected = expected.encode("utf-8")

        output = dedent(output).strip()
        output_lines = output.split("\n")
        if remove:
            output_lines = [line for line in output_lines if not any(r.match(line) for r in remove)]
        output = output.encode("utf-8")

        if len(expected_lines) != len(output_lines):
            assert (
                False
            ), "Different number of lines! Expected ===>\n{0}\n\nTo match ===>\n{1}".format(
                expected, output
            )

        ansi_escape = re.compile(r"\x1b[^m]*m")
        for a, b in zip(expected_lines, output_lines):
            if not isinstance(a, bytes):
                a = a.encode("utf-8")
            if not isinstance(b, bytes):
                b = re.sub(ansi_escape, "", b).encode("utf-8")
            else:
                b = re.sub(ansi_escape, "", b.decode("utf-8")).encode("utf-8")
            assert re.match(
                a, b
            ), "Didn't match! Expected ===>\n{0}\n\nTo match ===>\n{1}\n\n===>Failed matching {2} to {3}".format(
                expected, output, a, b
            )
