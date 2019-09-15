# coding: spec

from harpoon.executor import App

from contextlib import contextmanager
from tests.helpers import HarpoonCase
from delfick_project.norms import sb
from io import StringIO
import mock
import sys
import os

describe HarpoonCase, "App":
    describe "Cli parsing":
        it "replaces task and image with positional arguments":
            with self.a_temp_file() as config_location:
                argv = ["list_tasks", "blah", "--harpoon-config", config_location]
                app = App()
                args_obj, args_dict, extra_args = app.make_cli_parser().interpret_args(
                    argv, app.cli_categories
                )
                self.assertEqual(args_obj.harpoon_chosen_task, "list_tasks")
                self.assertEqual(args_obj.harpoon_chosen_image, "blah")
                self.assertEqual(args_dict["harpoon"]["chosen_task"], "list_tasks")
                self.assertEqual(args_dict["harpoon"]["chosen_image"], "blah")

        it "takes in HARPOON_CONFIG as the configuration file":
            with self.a_temp_file() as config_location:
                with self.modified_env(HARPOON_CONFIG=config_location):
                    argv = ["list_tasks", "blah"]
                    app = App()
                    args_obj, args_dict, extra_args = app.make_cli_parser().interpret_args(
                        argv, app.cli_categories
                    )
                    self.assertEqual(args_obj.harpoon_config.name, config_location)
                    self.assertEqual(args_dict["harpoon"]["config"].name, config_location)

        it "defaults image to sb.NotSpecified and tasks to list_tasks":
            with self.a_temp_file() as config_location:
                app = App()
                args_obj, args_dict, extra_args = app.make_cli_parser().interpret_args(
                    ["--harpoon-config", config_location], app.cli_categories
                )
                self.assertEqual(args_obj.harpoon_chosen_task, "list_tasks")
                self.assertEqual(args_obj.harpoon_chosen_image, sb.NotSpecified)
                self.assertEqual(args_dict["harpoon"]["chosen_task"], "list_tasks")
                self.assertEqual(args_dict["harpoon"]["chosen_image"], sb.NotSpecified)

        it "complains if no config exists":
            with self.a_temp_file() as config_location:
                os.remove(config_location)
                app = App()
                old_stderr = None
                try:
                    fake_stderr = StringIO()
                    sys.stderr, old_stderr = fake_stderr, sys.stderr
                    app.make_cli_parser().interpret_args(
                        ["--harpoon-config", config_location], app.cli_categories
                    )
                except SystemExit as error:
                    self.assertEqual(error.code, 2)
                    fake_stderr.seek(0)
                    self.assertEqual(
                        fake_stderr.read().split("\n")[-2],
                        "nosetests: error: argument --harpoon-config: can't open '{0}': [Errno 2] No such file or directory: '{0}'".format(
                            config_location
                        ),
                    )
                finally:
                    if old_stderr is not None:
                        sys.stderr = old_stderr

    describe "Execution":

        @contextmanager
        def setup_and_execute_app(self, argv, configuration):
            with self.a_temp_file() as config_location:
                with self.modified_env(HARPOON_CONFIG=config_location):
                    app = App()
                    args_obj, args_dict, extra_args = app.make_cli_parser().interpret_args(
                        argv, app.cli_categories
                    )

                    collector = mock.Mock(name="collector")
                    collector.configuration = configuration
                    FakeCollector = mock.Mock(name="Collector", return_value=collector)
                    docker_context = mock.Mock(name="docker_context")
                    logging_handler = mock.Mock(name="logging_handler")
                    setup_logging_theme = mock.Mock(name="setup_logging_theme")
                    docker_context_maker = mock.Mock(
                        name="docker_context_maker", return_value=docker_context
                    )

                    with mock.patch("harpoon.executor.Collector", FakeCollector):
                        with mock.patch("harpoon.executor.docker_context", docker_context_maker):
                            with mock.patch.object(app, "setup_logging_theme", setup_logging_theme):
                                yield collector, docker_context_maker, docker_context, app, setup_logging_theme, args_dict
                                app.execute(args_obj, args_dict, extra_args, logging_handler)

            FakeCollector.assert_called_once()

        it "sets up logging theme if term_colors is in the configuration":
            called = []
            default_task = "DEFAULT"

            def setup_logging_theme_func(logging_handler, colors):
                self.assertEqual(colors, "light")
                called.append(1)

            def task_runner(task):
                self.assertEqual(task, default_task)
                called.append(2)

            def prepare(filename, args_dict):
                configuration["harpoon"] = mock.Mock(name="harpoon")
                for key, val in args_dict["harpoon"].items():
                    setattr(configuration["harpoon"], key, val)
                configuration["task_runner"] = task_runner
                called.append(0)

            argv = [default_task]
            configuration = {"term_colors": "light"}

            with self.setup_and_execute_app(argv, configuration) as (
                collector,
                docker_context_Maker,
                docker_context,
                app,
                setup_logging_theme,
                args_dict,
            ):
                setup_logging_theme.side_effect = setup_logging_theme_func
                collector.prepare.side_effect = prepare

            self.assertEqual(called, [0, 1, 2])

        it "Sets up args_dict":
            called = []
            default_task = "DEFAULT"

            def setup_logging_theme_func(logging_handler, colors):
                # Doesn't get called
                called.append(0)

            def task_runner(task):
                args_dict = configuration["args_dict"]
                self.assertEqual(args_dict["harpoon"]["extra"], "one two --three")
                assert "docker_context_maker" in args_dict["harpoon"]
                assert "docker_context" in args_dict["harpoon"]
                assert "ran" not in args_dict
                args_dict["ran"] = True
                self.assertEqual(task, default_task)
                called.append(2)

            def prepare(filename, args_dict):
                configuration["harpoon"] = mock.Mock(name="harpoon")
                for key, val in args_dict["harpoon"].items():
                    setattr(configuration["harpoon"], key, val)
                configuration["args_dict"] = args_dict
                configuration["task_runner"] = task_runner
                called.append(1)

            argv = [default_task, "--", "one", "two", "--three"]
            configuration = {}

            with self.setup_and_execute_app(argv, configuration) as (
                collector,
                docker_context_maker,
                docker_context,
                app,
                setup_logging_theme,
                args_dict,
            ):
                self.assertEqual(args_dict["bash"], None)
                self.assertEqual(args_dict["command"], None)
                assert "docker_context_maker" not in args_dict
                assert "docker_context" not in args_dict
                assert "extra" not in args_dict["harpoon"]

                setup_logging_theme.side_effect = setup_logging_theme_func
                collector.prepare.side_effect = prepare

            self.assertEqual(called, [1, 2])

            self.assertEqual(args_dict["ran"], True)
            self.assertIs(args_dict["harpoon"]["docker_context_maker"], docker_context_maker)
            self.assertIs(args_dict["harpoon"]["docker_context"], docker_context)
