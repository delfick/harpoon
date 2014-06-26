import json

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

