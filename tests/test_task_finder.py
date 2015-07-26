# coding: spec

from harpoon.option_spec.task_objs import Task
from harpoon.task_finder import TaskFinder
from harpoon.collector import Collector
from harpoon.errors import BadTask

from tests.helpers import HarpoonCase

import mock
import json

describe HarpoonCase, "TaskFinder":
    it "takes in a collector":
        collector = mock.Mock(name="collector")
        configuration = mock.Mock(name="configuration")
        collector.configuration = configuration

        task_finder = TaskFinder(collector)
        self.assertEqual(task_finder.tasks, {})
        self.assertIs(task_finder.collector, collector)

    describe "image_finder":
        it "defaults to the chosen_image":
            chosen_image = mock.Mock(name="chosen_image")
            configuration = {"harpoon": type("Harpoon", (object, ), {"chosen_image": chosen_image})()}
            collector = mock.Mock(name="collector", configuration=configuration)

            task_finder = TaskFinder(collector)
            task_finder.tasks["blah"] = type("Task", (object, ), {})()
            self.assertIs(task_finder.image_finder("blah"), chosen_image)

        it "chooses the image on the task":
            chosen_image = mock.Mock(name="chosen_image")
            actual_image = mock.Mock(name="actual_image")
            configuration = {"harpoon": type("Harpoon", (object, ), {"chosen_image": chosen_image})()}
            collector = mock.Mock(name="collector", configuration=configuration)

            task_finder = TaskFinder(collector)
            task_finder.tasks["blah"] = type("Task", (object, ), {"image": actual_image})()
            self.assertIs(task_finder.image_finder("blah"), actual_image)

    describe "task_runner":
        it "complains if the task doesn't exist":
            task = mock.Mock(name="task")
            with self.fuzzyAssertRaisesError(BadTask, "Unknown task", task=task, available=["one", "two"]):
                task_finder = TaskFinder(mock.Mock(name="collector"))
                task_finder.tasks = {"one": mock.Mock(name="one"), "two": mock.Mock(name="two")}
                task_finder.task_runner(task)

        it "runs the task":
            image = mock.Mock(name="image")
            task = mock.Mock(name="task", image=image)

            collector = mock.Mock(name="collector")
            collector.configuration = {"harpoon": type("Harpoon", (object, ), {"chosen_image": mock.Mock(name="chosen_image")})()}

            task_finder = TaskFinder(collector)
            task_finder.tasks = {"blah": task}

            available_actions = mock.Mock(name="available_actions")
            with mock.patch("harpoon.task_finder.available_actions", available_actions):
                task_finder.task_runner("blah", one=1, two=2)
                task.run.assert_called_once_with(collector, image, available_actions, {"blah": task}, one=1, two=2)

    describe "default_tasks":
        it "returns a dictionary of name to Task object for all the names in default_actions":
            def one_func():
                """le description of stuff"""
            def two_func():
                """trees and things"""
            available_actions = {"one": one_func, "two": two_func}
            default_actions = ["one", "two"]

            with mock.patch("harpoon.actions.available_actions", available_actions):
                with mock.patch("harpoon.task_finder.default_actions", default_actions):
                    base = TaskFinder(mock.Mock(name="collector")).default_tasks()
                    self.assertEqual(base
                        , { "one": Task(action="one", description="le description of stuff", label="Harpoon")
                          , "two": Task(action="two", description="trees and things", label="Harpoon")
                          }
                        )

    describe "Finding tasks":
        it "returns default tasks with overrides added":
            configuration = {"images": {}}
            collector = mock.Mock(name="collector", configuration=configuration)
            task_finder = TaskFinder(collector)

            tasks = {"one": Task(action="one", description="one"), "two": Task(action="two", description="two")}
            overrides = {"three": Task(action="three", description="three")}
            default_tasks = mock.Mock(name="default_tasks", return_value=tasks)

            all_tasks = {}
            all_tasks.update(tasks)
            all_tasks.update(overrides)
            with mock.patch.object(task_finder, "default_tasks", default_tasks):
                self.assertEqual(task_finder.find_tasks(overrides), all_tasks)
                self.assertEqual(task_finder.tasks, all_tasks)

        it "finds tasks attached to images":
            configuration = {
                  "images":
                  { "blah":
                    { "commands": "FROM ubuntu:14.04"
                    , "tasks": {"one": {}}
                    }
                  , "stuff":
                    { "commands": "FROM ubuntu:14.04"
                    , "tasks": {"two": {"description": "not much"}}
                    }
                  , "other":
                    { "commands": "FROM ubuntu:14.04"
                    }
                  }
                }

            with self.a_temp_file(json.dumps(configuration)) as filename:
                default_tasks = mock.Mock(name="default_tasks", return_value={})
                collector = Collector()
                collector.prepare(filename, {"harpoon": {}, "bash": None, "command": None})
                task_finder = TaskFinder(collector)

                with mock.patch.object(task_finder, "default_tasks", default_tasks):
                    tasks = task_finder.find_tasks({})
                    self.assertEqual(sorted(list(tasks.keys())), sorted(["one", "two"]))
                    self.assertEqual(tasks["one"].image, "blah")
                    self.assertEqual(tasks["two"].image, "stuff")

