# coding: spec

from harpoon.overview import Harpoon

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
from option_merge import MergedOptions
from contextlib import contextmanager
import mock
import yaml
import uuid
import os

describe HarpoonCase, "Collecting configuration":
    before_each:
        self.folder = self.make_temp_dir()
        self.docker_context = mock.Mock(name="docker_context")

    def make_config(self, options, folder=None):
        if folder is None:
            folder = self.folder
        location = os.path.join(folder, str(uuid.uuid1()))

        yaml.dump(options, open(location, 'w'))
        return location

    @contextmanager
    def make_harpoon(self, config, home_dir_configuration=None, logging_handler=None):
        if home_dir_configuration is None:
            home_dir_configuration = (None, None)

        home_dir_configuration_mock = mock.Mock(name="home_dir_configuration", spec=[])
        home_dir_configuration_mock.return_value = home_dir_configuration
        harpoon_kls = type("HarpoonSub", (Harpoon, ), {"home_dir_configuration": home_dir_configuration_mock})
        yield harpoon_kls(config, self.docker_context, logging_handler=logging_handler)

    it "puts in __mtime__ and images":
      config = self.make_config({})
      mtime = os.path.getmtime(config)
      with self.make_harpoon(config) as harpoon:
          self.assertIs(type(harpoon.configuration), MergedOptions)
          self.assertIs(type(harpoon.configuration["images"]), MergedOptions)
          self.assertEqual(harpoon.configuration['__mtime__'], mtime)
          self.assertEqual(dict(harpoon.configuration['images'].items()), {})
          self.assertEqual(sorted(harpoon.configuration.keys()), sorted(["__mtime__", "images"]))

    it "includes configuration from the home directory":
        config = self.make_config({"a":1, "b":2})
        home_config = self.make_config({"a":3, "c":4})
        with self.make_harpoon(config, (home_config, yaml.load(open(home_config)))) as harpoon:
            self.assertEqual(sorted(harpoon.configuration.keys()), sorted(['a', 'b', 'c', '__mtime__', 'images']))
            self.assertEqual(harpoon.configuration['a'], 1)
            self.assertEqual(harpoon.configuration['b'], 2)
            self.assertEqual(harpoon.configuration['c'], 4)

