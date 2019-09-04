# coding: spec

from harpoon.errors import ImageDepCycle
from harpoon.layers import Layers

from noseOfYeti.tokeniser.support import noy_sup_setUp, noy_sup_tearDown
from tests.helpers import HarpoonCase
import mock
import six

if six.PY3:
    from itertools import zip_longest
else:

    def zip_longest(lst1, lst2):
        return map(None, lst1, lst2)


import nose

describe HarpoonCase, "ImageLayer":
    before_each:
        self.image1 = mock.Mock(name="image1")
        self.image2 = mock.Mock(name="image2")
        self.image3 = mock.Mock(name="image3")
        self.images = {"image1": self.image1, "image2": self.image2, "image3": self.image3}
        self.instance = Layers(self.images)

    def assertCallsSame(self, mock, expected):
        print("Printing calls as <done> || <expected>")
        print("----")

        call_list = mock.call_args_list
        for did, wanted in zip_longest(call_list, expected):
            print("     {0} || {1}".format(did, wanted))
            print("--")

        self.assertEqual(len(call_list), len(expected))
        mock.assert_has_calls(expected)

    it "takes a list of images":
        images = mock.Mock(name="images")
        layers = Layers(images)
        self.assertIs(layers.images, images)

    it "sets all images to the images it received if not given one otherwise":
        images = mock.Mock(name="images")
        layers = Layers(images)
        self.assertIs(layers.all_images, images)

    it "takes a dictionary for all the images":
        images = mock.Mock(name="images")
        all_images = mock.Mock(name="all_images")
        layers = Layers(images, all_images=all_images)
        self.assertIs(layers.images, images)
        self.assertIs(layers.all_images, all_images)

    describe "Resetting the instance":
        it "resets layered to an empty list":
            self.instance._layered = mock.Mock(name="layered")
            self.instance.reset()
            self.assertEqual(self.instance._layered, [])

        it "resets accounted to an empty dict":
            self.instance.accounted = mock.Mock(name="accounted")
            self.instance.reset()
            self.assertEqual(self.instance.accounted, {})

    describe "Getting layered":
        it "has a property for converting _layered into a list of list of tuples":
            self.instance._layered = [["one"], ["two", "three"], ["four"]]
            self.instance.images = ["one", "two", "three", "four"]
            self.instance.all_images = {"one": 1, "two": 2, "three": 3, "four": 4}
            self.assertEqual(
                self.instance.layered, [[("one", 1)], [("two", 2), ("three", 3)], [("four", 4)]]
            )

    describe "Adding layers":
        before_each:
            self.all_images = {}
            for i in range(1, 10):
                name = "image{0}".format(i)
                obj = mock.Mock(name=name)
                obj.dependencies = lambda a: []
                setattr(self, name, obj)
                self.all_images[name] = obj
            self.images = self.all_images.keys()
            self.instance = Layers(self.images, self.all_images)

        def assertLayeredSame(self, layers, expected):
            if not layers.layered:
                layers.add_all_to_layers()
            created = layers.layered

            print("Printing expected and created as each layer on a new line.")
            print("    the line starting with || is the expected")
            print("    the line starting with >> is the created")
            print("----")

            for expcted, crted in zip_longest(expected, created):
                print("    || {0}".format(sorted(expcted) if expcted else None))
                print("    >> {0}".format(sorted(crted) if crted else None))
                print("--")

            error_msg = "Expected created layered to have {0} layers. Only has {1}".format(
                len(expected), len(created)
            )
            self.assertEqual(len(created), len(expected), error_msg)

            for index, layer in enumerate(created):
                nxt = expected[index]
                self.assertEqual(sorted(layer) if layer else None, sorted(nxt) if nxt else None)

        it "has a method for adding all the images":
            add_to_layers = mock.Mock(name="add_to_layers")
            with mock.patch.object(self.instance, "add_to_layers", add_to_layers):
                self.instance.add_all_to_layers()
            self.assertCallsSame(add_to_layers, sorted([mock.call(image) for image in self.images]))

        it "does nothing if the image is already in accounted":
            self.assertEqual(self.instance._layered, [])
            self.instance.accounted["image1"] = True

            self.image1.dependencies = []
            self.instance.add_to_layers("image1")
            self.assertEqual(self.instance._layered, [])
            self.assertEqual(self.instance.accounted, {"image1": True})

        it "adds image to accounted if not already there":
            self.assertEqual(self.instance._layered, [])
            self.assertEqual(self.instance.accounted, {})

            self.image1.dependencies = lambda a: []
            self.instance.add_to_layers("image1")
            self.assertEqual(self.instance._layered, [["image1"]])
            self.assertEqual(self.instance.accounted, {"image1": True})

        it "complains about cyclic dependencies":
            self.image1.dependencies = lambda a: ["image2"]
            self.image2.dependencies = lambda a: ["image1"]

            with self.fuzzyAssertRaisesError(ImageDepCycle, chain=["image1", "image2", "image1"]):
                self.instance.add_to_layers("image1")

            self.instance.reset()
            with self.fuzzyAssertRaisesError(ImageDepCycle, chain=["image2", "image1", "image2"]):
                self.instance.add_to_layers("image2")

        describe "Dependencies":
            before_each:
                self.fake_add_to_layers = mock.Mock(name="add_to_layers")
                original = self.instance.add_to_layers
                self.fake_add_to_layers.side_effect = lambda *args, **kwargs: original(
                    *args, **kwargs
                )
                self.patcher = mock.patch.object(
                    self.instance, "add_to_layers", self.fake_add_to_layers
                )
                self.patcher.start()

            after_each:
                self.patcher.stop()

            describe "Simple dependencies":
                it "adds all images to the first layer if they don't have dependencies":
                    self.assertLayeredSame(self.instance, [self.all_images.items()])

                it "adds image after it's dependency if one is specified":
                    self.image3.dependencies = lambda a: ["image1"]
                    cpy = dict(self.all_images.items())
                    del cpy["image3"]
                    expected = [cpy.items(), [("image3", self.image3)]]
                    self.assertLayeredSame(self.instance, expected)

                it "works with images sharing the same dependency":
                    self.image3.dependencies = lambda a: ["image1"]
                    self.image4.dependencies = lambda a: ["image1"]
                    self.image5.dependencies = lambda a: ["image1"]

                    cpy = dict(self.all_images.items())
                    del cpy["image3"]
                    del cpy["image4"]
                    del cpy["image5"]
                    expected = [
                        cpy.items(),
                        [("image3", self.image3), ("image4", self.image4), ("image5", self.image5)],
                    ]
                    self.assertLayeredSame(self.instance, expected)

            describe "Complex dependencies":

                it "works with more than one level of dependency":
                    self.image3.dependencies = lambda a: ["image1"]
                    self.image4.dependencies = lambda a: ["image1"]
                    self.image5.dependencies = lambda a: ["image1"]
                    self.image9.dependencies = lambda a: ["image4"]

                    #      9
                    #      |
                    # 3    4    5
                    # \    |    |
                    #  \   |   /
                    #   \  |  /
                    #    --1--         2     6     7     8

                    expected_calls = [
                        mock.call("image1"),
                        mock.call("image2"),
                        mock.call("image3"),
                        mock.call("image1", ["image3"]),
                        mock.call("image4"),
                        mock.call("image1", ["image4"]),
                        mock.call("image5"),
                        mock.call("image1", ["image5"]),
                        mock.call("image6"),
                        mock.call("image7"),
                        mock.call("image8"),
                        mock.call("image9"),
                        mock.call("image4", ["image9"]),
                    ]

                    expected = [
                        [
                            ("image1", self.image1),
                            ("image2", self.image2),
                            ("image6", self.image6),
                            ("image7", self.image7),
                            ("image8", self.image8),
                        ],
                        [("image3", self.image3), ("image4", self.image4), ("image5", self.image5)],
                        [("image9", self.image9)],
                    ]

                    self.instance.add_all_to_layers()
                    self.assertCallsSame(self.fake_add_to_layers, expected_calls)
                    self.assertLayeredSame(self.instance, expected)

                it "handles more complex dependencies":
                    self.image1.dependencies = lambda a: ["image2"]
                    self.image2.dependencies = lambda a: ["image3", "image4"]
                    self.image4.dependencies = lambda a: ["image5"]
                    self.image6.dependencies = lambda a: ["image9"]
                    self.image7.dependencies = lambda a: ["image6"]
                    self.image9.dependencies = lambda a: ["image4", "image8"]

                    #                     7
                    #                     |
                    #     1               6
                    #     |               |
                    #     2               9
                    #   /   \          /     \
                    # /       4   ----        |
                    # |       |               |
                    # 3       5               8

                    expected_calls = [
                        mock.call("image1"),
                        mock.call("image2", ["image1"]),
                        mock.call("image3", ["image1", "image2"]),
                        mock.call("image4", ["image1", "image2"]),
                        mock.call("image5", ["image1", "image2", "image4"]),
                        mock.call("image2"),
                        mock.call("image3"),
                        mock.call("image4"),
                        mock.call("image5"),
                        mock.call("image6"),
                        mock.call("image9", ["image6"]),
                        mock.call("image4", ["image6", "image9"]),
                        mock.call("image8", ["image6", "image9"]),
                        mock.call("image7"),
                        mock.call("image6", ["image7"]),
                        mock.call("image8"),
                        mock.call("image9"),
                    ]

                    expected = [
                        [("image3", self.image3), ("image5", self.image5), ("image8", self.image8)],
                        [("image4", self.image4)],
                        [("image2", self.image2), ("image9", self.image9)],
                        [("image1", self.image1), ("image6", self.image6)],
                        [("image7", self.image7)],
                    ]

                    self.instance.add_all_to_layers()
                    self.assertCallsSame(self.fake_add_to_layers, expected_calls)
                    self.assertLayeredSame(self.instance, expected)

                it "only gets layers for the images specified":
                    self.image1.dependencies = lambda a: ["image2"]
                    self.image2.dependencies = lambda a: ["image3", "image4"]
                    self.image4.dependencies = lambda a: ["image5"]
                    self.image6.dependencies = lambda a: ["image9"]
                    self.image7.dependencies = lambda a: ["image6"]
                    self.image9.dependencies = lambda a: ["image4", "image8"]

                    #                     7
                    #                     |
                    #     1               6
                    #     |               |
                    #     2               9
                    #   /   \          /     \
                    # /       4   ----        |
                    # |       |               |
                    # 3       5               8

                    # Only care about 3, 4 and 6
                    # So should only get layers for
                    #
                    #                     6
                    #                     |
                    #                     9
                    #                  /     \
                    #         4   ----        |
                    #         |               |
                    # 3       5               8

                    expected_calls = [
                        mock.call("image3"),
                        mock.call("image4"),
                        mock.call("image5", ["image4"]),
                        mock.call("image6"),
                        mock.call("image9", ["image6"]),
                        mock.call("image4", ["image6", "image9"]),
                        mock.call("image8", ["image6", "image9"]),
                    ]

                    expected = [
                        [("image3", self.image3), ("image5", self.image5), ("image8", self.image8)],
                        [("image4", self.image4)],
                        [("image9", self.image9)],
                        [("image6", self.image6)],
                    ]

                    self.instance.images = ["image3", "image4", "image6"]
                    self.instance.add_all_to_layers()
                    self.assertCallsSame(self.fake_add_to_layers, expected_calls)
                    self.assertLayeredSame(self.instance, expected)
