# coding: spec

from harpoon.option_spec.image_objs import Image, Command
from harpoon.option_spec.harpoon_specs import Harpoon
from harpoon.option_spec.task_objs import Task
from harpoon.executor import CliParser
from harpoon.overview import Overview

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

    def make_config(self, options, folder=None, filename=None):
        if folder is None:
            folder = self.folder

        if filename is None:
            filename = str(uuid.uuid1())
        location = os.path.join(folder, filename)

        yaml.dump(options, open(location, 'w'))
        return location

    @contextmanager
    def make_overview(self, config, home_dir_configuration=None, logging_handler=None, activate_converters=False):
        if home_dir_configuration is None:
            if hasattr(self, "home_dir_configuration"):
                home_dir_configuration = self.home_dir_configuration
            else:
                home_dir_configuration = self.make_config({})

        home_dir_configuration_location = mock.Mock(name="home_dir_configuration_location", spec=[])
        home_dir_configuration_location.return_value = home_dir_configuration
        overview_kls = type("OverviewSub", (Overview, ), {"home_dir_configuration_location": home_dir_configuration_location})
        overview = overview_kls(config, logging_handler=logging_handler)
        if activate_converters:
            overview.configuration.converters.activate()
        yield overview

    it "puts in mtime and images":
        config = self.make_config({"images": { "blah": {"commands": ["FROM nowhere"]}}})
        mtime = os.path.getmtime(config)
        with self.make_overview(config) as overview:
            self.assertIs(type(overview.configuration), MergedOptions)
            self.assertIs(type(overview.configuration["images"]), MergedOptions)
            self.assertEqual(overview.configuration['mtime'](), mtime)
            self.assertEqual(dict(overview.configuration['images'].items()), {"blah": overview.configuration["images.blah"]})
            self.assertEqual(sorted(overview.configuration.keys()), sorted(["mtime", "images"]))

    it "includes configuration from the home directory":
        config = self.make_config({"a":1, "b":2, "images": {"meh": {}}})
        home_config = self.make_config({"a":3, "c":4})
        with self.make_overview(config, home_config) as overview:
            self.assertEqual(sorted(overview.configuration.keys()), sorted(['a', 'b', 'c', 'mtime', 'images']))
            self.assertEqual(overview.configuration['a'], 1)
            self.assertEqual(overview.configuration['b'], 2)
            self.assertEqual(overview.configuration['c'], 4)

    it "sets up converters for overview":
        config = self.make_config({"harpoon": {}})
        with self.make_overview(config, activate_converters=True) as overview:
            self.assertIs(type(overview.configuration["harpoon"]), Harpoon)

    it "sets up converters for tasks":
        config = self.make_config({"images": {"blah": {"commands": ["FROM nowhere"], "tasks": {"a_task": {}}}}})
        with self.make_overview(config, activate_converters=True) as overview:
            self.assertIs(type(overview.configuration["images.blah.tasks"]["a_task"]), Task)

    it "sets up converters for images":
        config = self.make_config({"harpoon": {}, "config_root": ".", "images": {"blah": {"commands": ["FROM nowhere"]}}})
        with self.make_overview(config, activate_converters=True) as overview:
            self.assertIs(type(overview.configuration["images.blah"]), Image)

    it "collects configuration from __images_from__":
        with self.a_temp_dir() as images_from:
            config1 = self.make_config({"commands": ["FROM somewhere"]}, folder=images_from, filename="one.yml")
            config2 = self.make_config({"commands": ["FROM somewhere_else"]}, folder=images_from, filename="two.yml")

            config = self.make_config({"harpoon": {}, "config_root": ".", "images": {"__images_from__": images_from}})
            with self.make_overview(config, activate_converters=True) as overview:
                self.assertIs(type(overview.configuration["images.one"]), Image)
                self.assertIs(type(overview.configuration["images.two"]), Image)

                self.assertEqual(overview.configuration["images.one"].commands.docker_lines, "FROM somewhere")
                self.assertEqual(overview.configuration["images.two"].commands.docker_lines, "FROM somewhere_else")

        it "merges options from the root into each image":
            config = {
                  "context": {"parent_dir": "a_tree"}
                , "harpoon": {}, "config_root": self.folder
                , "images":
                  { "one": {"commands": ["FROM somewhere"]}
                  , "two": {"commands": ["FROM somewhere_else"]}
                  }
                }

            with self.make_overview(config, activate_converters=True) as overview:
                for image in overview.configuration["images"].values():
                    self.assertEqual(image.context.parent_dir, "a_tree")

    describe "Task Option merging":
        @contextmanager
        def a_fake_action(self, config, argv):
            called = []
            config = self.make_config(config)
            argv.extend(["--harpoon-config", config])
            with self.make_overview(config, activate_converters=True) as overview:
                def action(ovw, conf, images, image):
                    self.assertIs(ovw, overview)
                    called.append((ovw, conf, images, image))
                action.needs_image = True
                action.needs_images = True

                _, cli_args = CliParser().interpret_args(argv, no_docker=True)
                overview.start(cli_args, available_tasks={"run": action})
                yield called[0]

            self.assertEqual(len(called), 1)

        it "inserts options from the task with only the image associated with the task":
            with self.a_temp_dir() as parent_dir:
                task_options = {"context": {"parent_dir": self.folder}}
                config = {
                      "context": {"parent_dir": parent_dir}
                    , "images":
                      { "one": {"commands": ["FROM somewhere"]}
                      , "two": {"commands": ["FROM somewhere_else"], "tasks": {"a_task": {"options": task_options}}}
                      }
                    }

                with self.a_fake_action(config, ["a_task"]) as (overview, conf, images, image):
                    self.assertIs(image, overview.configuration["images.two"])
                    self.assertEqual(images["one"].context.parent_dir, parent_dir)
                    self.assertEqual(images["two"].context.parent_dir, self.folder)


        it "inserts overrides from task for all images":
            task_options = {"vars": {"one": 1}}
            config = {
                  "vars": {"one": "one"}
                , "images":
                  { "one": {"commands": [["FROM", "{vars.one}"]]}
                  , "two": {"commands": [["FROM", "{vars.one}"]], "tasks": {"a_task": {"overrides": task_options}}}
                  }
                }

            with self.a_fake_action(config, ["a_task"]) as (overview, conf, images, image):
                self.assertIs(image, overview.configuration["images.two"])
                self.assertEqual(images["one"].commands.docker_lines, "FROM 1")
                self.assertEqual(images["two"].commands.docker_lines, "FROM 1")

