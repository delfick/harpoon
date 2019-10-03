# coding: spec

from harpoon.option_spec.harpoon_specs import Harpoon, HarpoonSpec
from harpoon.option_spec import image_objs, command_objs
from harpoon.collector import Collector

from tests.helpers import HarpoonCase

from delfick_project.option_merge import MergedOptions
from delfick_project.errors_pytest import assertRaises
from delfick_project.norms import sb, dictobj
from textwrap import dedent
from getpass import getpass
from unittest import mock
import json
import os

describe HarpoonCase, "Collector":
    describe "clone":
        it "has a new harpoon object":
            configuration = {"images": {"blah": {"commands": "FROM ubuntu:14.04"}}}
            with self.a_temp_file(json.dumps(configuration)) as filename:
                collector = Collector()
                collector.prepare(
                    filename,
                    {
                        "harpoon": {"chosen_image": "blah"},
                        "bash": None,
                        "command": None,
                        "assume_role": None,
                    },
                )
                collector2 = collector.clone({"harpoon": {"chosen_image": "other"}})

                assert collector.configuration["harpoon"] != collector2.configuration["harpoon"]
                assert collector.configuration["harpoon"].chosen_image == "blah"
                assert collector2.configuration["harpoon"].chosen_image == "other"

    describe "prepare":
        it "adds some items to the configuration from the args_dict":
            bash = "bash command"
            extra = "extra commands after the --"
            command = "Command command"
            args_dict = {"harpoon": {}}

            configuration = {"images": {"blah": {"commands": "FROM ubuntu:14.04"}}}
            with self.a_temp_file(json.dumps(configuration)) as filename:
                collector = Collector()
                raw_config = collector.collect_configuration(filename, args_dict)
                for thing in ("configuration", "$@", "bash", "command", "harpoon"):
                    assert (
                        thing not in raw_config
                    ), "expected {0} to not be in configuration".format(thing)

                args_dict = {
                    "harpoon": {"extra": extra},
                    "bash": bash,
                    "command": command,
                    "assume_role": None,
                }
                collector.prepare(filename, args_dict)

                # Done by option_merge
                assert collector.configuration["getpass"] == getpass
                assert collector.configuration["args_dict"].as_dict() == args_dict
                assert collector.configuration["collector"] == collector
                assert collector.configuration["config_root"] == os.path.dirname(filename)

                # Done by bespin
                assert collector.configuration["$@"] == extra
                assert collector.configuration["bash"] == bash
                assert collector.configuration["command"] == command
                assert collector.configuration["harpoon"]["extra"] == extra

        it "adds task_runner from a TaskFinder to the configuration and finds tasks":
            task_finder = mock.Mock(name="task_finder")
            FakeTaskFinder = mock.Mock(name="TaskFinder", return_value=task_finder)
            configuration = {"images": {"blah": {"commands": "FROM ubuntu:14.04"}}}
            with self.a_temp_file(json.dumps(configuration)) as filename:
                with mock.patch("harpoon.collector.TaskFinder", FakeTaskFinder):
                    collector = Collector()
                    args_dict = {"harpoon": {}, "bash": None, "command": None, "assume_role": None}
                    collector.prepare(filename, args_dict)
                    task_finder.find_tasks.assert_called_once_with({})

                    assert len(task_finder.task_runner.mock_calls) == 0
                    collector.configuration["task_runner"]("blah")
                    task_finder.task_runner.assert_called_once_with("blah")

                    FakeTaskFinder.assert_called_once_with(collector)

    describe "Configuration":
        describe "start configuration":
            it "Returns a MergedOptions that doesn't prefix dictobjs":

                class Thing(dictobj):
                    fields = ["one", "two"]

                thing = Thing(1, 2)
                options = Collector().start_configuration()
                options.update({"three": {"four": {"5": "6"}}, "seven": thing})

                assert type(options["three"]) is MergedOptions
                assert options["three"].as_dict() == {"four": {"5": "6"}}

                assert type(options["seven"]) is Thing
                assert options["seven"] == {"one": 1, "two": 2}

        describe "Reading a file":
            it "reads a yaml file and returns it as a dictionary":
                config = dedent(
                    """
                    ---

                    one: 1
                    two:
                        three: 3
                        four: 4
                    five: |
                        six
                        seven
                        eight
                    nine: >
                        ten
                        eleven
                        twelve
                """
                ).strip()

                with self.a_temp_file(config) as filename:
                    collector = Collector()
                    readed = collector.read_file(filename)
                    assert readed == {
                        "one": 1,
                        "two": {"three": 3, "four": 4},
                        "five": "six\nseven\neight\n",
                        "nine": "ten eleven twelve",
                    }

            it "complains about scanner errors":
                config = dedent(
                    """
                    ---

                    five: |>
                        six
                        seven
                        eight
                """
                ).strip()

                with self.a_temp_file(config) as filename:
                    collector = Collector()
                    with assertRaises(
                        collector.BadFileErrorKls,
                        "Failed to read yaml",
                        location=filename,
                        error_type="ScannerError",
                        error='did not find expected comment or line break  in "{0}", line 3, column 8'.format(
                            filename
                        ),
                    ):
                        readed = collector.read_file(filename)

            it "complains about parser errors":
                config = dedent(
                    """
                    ---

                    five: {one
                """
                ).strip()

                with self.a_temp_file(config) as filename:
                    collector = Collector()
                    with assertRaises(
                        collector.BadFileErrorKls,
                        "Failed to read yaml",
                        location=filename,
                        error_type="ParserError",
                        error="did not find expected ',' or '}}'  in \"{0}\", line 4, column 1".format(
                            filename
                        ),
                    ):
                        readed = collector.read_file(filename)

        describe "Adding configuration":
            it "merges from extra_files":
                config1 = dedent(
                    """
                    ---

                    two:
                        three: 5
                        six: 6
                """
                ).strip()

                with self.a_temp_file(config1) as filename1:
                    config2 = dedent(
                        """
                        ---

                        harpoon:
                            extra_files: {0}
                        one: 1
                        two:
                            three: 3
                            four: 4
                        five: |
                            six
                            seven
                            eight
                        nine: >
                            ten
                            eleven
                            twelve
                    """.format(
                            filename1
                        )
                    ).strip()

                    with self.a_temp_file(config2) as filename2:
                        collector = Collector()
                        configuration = collector.collect_configuration(filename2, {})
                        as_dict = configuration.as_dict()
                        assert as_dict == {
                            "one": 1,
                            "two": {"three": 5, "six": 6, "four": 4},
                            "five": "six\nseven\neight\n",
                            "nine": "ten eleven twelve",
                            "harpoon": {"extra_files": filename1},
                            "collector": collector,
                            "getpass": getpass,
                            "args_dict": {},
                            "config_root": os.path.dirname(filename2),
                            "authentication": sb.NotSpecified,
                            "content": sb.NotSpecified,
                        }

            it "collects files in folders specified by images.__images_from__":
                root, folders = self.setup_directory(
                    {
                        "one": {
                            "two": {"three.yml": "", "four.yml": ""},
                            "five": [],
                            "six": {"seven.yml": ""},
                            "eight.yml": "",
                        },
                        "two": {"notseen.yml": ""},
                    }
                )
                collect_another_source = mock.Mock(name="collect_another_source")

                collector = Collector()
                configuration = collector.start_configuration()
                done = {}
                result = {"images": {"__images_from__": [folders["one"]["/folder/"]]}}
                src = mock.Mock(name="src")
                collector.add_configuration(
                    configuration, collect_another_source, done, result, src
                )

                assert sorted(collect_another_source.mock_calls) == (
                    sorted(
                        [
                            mock.call(
                                folders["one"]["eight.yml"]["/file/"], prefix=["images", "eight"]
                            ),
                            mock.call(
                                folders["one"]["two"]["four.yml"]["/file/"],
                                prefix=["images", "four"],
                            ),
                            mock.call(
                                folders["one"]["two"]["three.yml"]["/file/"],
                                prefix=["images", "three"],
                            ),
                            mock.call(
                                folders["one"]["six"]["seven.yml"]["/file/"],
                                prefix=["images", "seven"],
                            ),
                        ]
                    )
                )

            it "successfully prefixes included __images_from__":
                config = json.dumps({"commands": "FROM ubuntu:14.04"})
                root, folders = self.setup_directory(
                    {
                        "one": {
                            "two": {"three.yml": config, "four.yml": config},
                            "five": [],
                            "six": {"seven.yml": config},
                        },
                        "two": {"notseen.yml": config},
                    }
                )
                configuration = {"images": {"__images_from__": folders["one"]["/folder/"]}}
                with self.a_temp_file(json.dumps(configuration)) as filename:
                    collector = Collector()
                    collector.prepare(
                        filename,
                        {"harpoon": {}, "bash": None, "command": None, "assume_role": None},
                    )
                    cfg = json.loads(config)

                    cfg_three = dict(cfg)
                    cfg_four = dict(cfg)
                    cfg_seven = dict(cfg)

                    cfg_three["config_root"] = folders["one"]["two"]["/folder/"]
                    cfg_four["config_root"] = folders["one"]["two"]["/folder/"]
                    cfg_seven["config_root"] = folders["one"]["six"]["/folder/"]
                    assert collector.configuration["images"].as_dict() == {
                        "three": cfg_three,
                        "four": cfg_four,
                        "seven": cfg_seven,
                    }

        describe "Converters":
            it "registers a harpoon converter":
                collector = Collector()
                configuration = collector.start_configuration()
                configuration["harpoon"] = {}
                configuration.converters.activate()
                assert configuration["harpoon"].as_dict() == {}
                assert type(configuration["harpoon"]) != Harpoon

                configuration.update({"args_dict": {"harpoon": configuration["harpoon"]}})
                collector.extra_configuration_collection(configuration)
                configuration.converters.activate()
                assert type(configuration["harpoon"]) == Harpoon

            it "registers image converters for each image":
                the_harpoon_spec = mock.Mock(name="the_harpoon_spec")
                harpoon_spec = mock.Mock(name="harpoon_spec", harpoon_spec=the_harpoon_spec)
                the_harpoon_spec.normalise.return_value = mock.Mock(
                    name="harpoon", addons=[], spec=["addons"]
                )

                FakeHarpoonSpec = mock.Mock(name="HarpoonSpec", return_value=harpoon_spec)
                make_image_converters = mock.Mock(name="make_image_converters")

                collector = Collector()
                configuration = collector.start_configuration()
                configuration["images"] = {"blah": {}, "stuff": {}, "other": {}}
                configuration.update({"args_dict": {"harpoon": {}}})
                with mock.patch("harpoon.collector.HarpoonSpec", FakeHarpoonSpec):
                    with mock.patch.object(
                        collector, "make_image_converters", make_image_converters
                    ):
                        collector.extra_configuration_collection(configuration)

                assert sorted(make_image_converters.mock_calls) == (
                    sorted(
                        [
                            mock.call("blah", configuration, harpoon_spec),
                            mock.call("stuff", configuration, harpoon_spec),
                            mock.call("other", configuration, harpoon_spec),
                        ]
                    )
                )

        describe "Image converters":
            it "installs a converter for the image itself and for the group of tasks":
                normalised_image = mock.Mock(name="normalised_image")
                normalised_tasks = mock.Mock(name="normalised_tasks")
                t1 = mock.Mock(name="t1")
                t2 = mock.Mock(name="t2")
                normalised_tasks.values.return_value = [t1, t2]

                harpoon_spec = mock.Mock(name="harpoon_spec")
                harpoon_spec.image_spec = mock.Mock(name="image_spec")
                harpoon_spec.image_spec.normalise.return_value = normalised_image

                harpoon_spec.tasks_spec = mock.Mock(name="tasks_spec")
                harpoon_spec.tasks_spec.return_value.normalise.return_value = normalised_tasks

                collector = Collector()
                configuration = collector.start_configuration()
                configuration["harpoon"] = {}
                configuration["images"] = {
                    "blah": {"commands": "FROM ubuntu:14.04", "tasks": {"one": {}}}
                }
                configuration.converters.activate()

                collector.make_image_converters("blah", configuration, harpoon_spec)
                assert configuration["images"]["blah"] is normalised_image
                assert configuration[["images", "blah", "tasks"]] is normalised_tasks
                assert t1.image == "blah"
                assert t2.image == "blah"

            it "uses root of configuration with image as an override for the image converter":
                collector = Collector()
                configuration = collector.start_configuration()
                configuration["harpoon"] = {}
                configuration["context"] = False
                configuration["config_root"] = "."
                configuration["images"] = {
                    "blah": {
                        "commands": [["FROM", "{__image__.vars.blah}-{__image__.vars.stuff}"]],
                        "vars": {"stuff": 2},
                    }
                }
                configuration["vars"] = {"blah": 30, "stuff": 40}
                configuration.converters.activate()
                collector.make_image_converters("blah", configuration, HarpoonSpec())

                assert configuration["images"]["blah"].commands.orig_commands == [
                    [command_objs.Command(("FROM", "30-2"))]
                ]
                assert configuration["images"]["blah"].context.enabled == False
