# coding: spec

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.errors import BadSpec, BadSpecValue
from harpoon.option_spec.task_objs import Task

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
from input_algorithms.meta import Meta
from option_merge import MergedOptions
import mock

describe HarpoonCase, "HarpoonSpec":
    before_each:
        self.docker_context = mock.Mock(name="docker_context")
        self.harpoon = mock.Mock(name="harpoon", docker_context=self.docker_context)
        self.meta = Meta({"harpoon": self.harpoon}, [])

    it "can get a fake Image":
        with self.a_temp_dir() as directory:
            harpoon = mock.Mock(name="harpoon")
            everything = MergedOptions.using({"config_root": directory, "_key_name_1": "blah", "harpoon": harpoon})
            meta = Meta(everything, [])
            fake = HarpoonSpec().image_spec.fake_filled(meta, with_non_defaulted=True)
            self.assertEqual(fake.context.parent_dir, directory)
            self.assertEqual(fake.name, "blah")

        as_dict = fake.as_dict()
        self.assertEqual(type(as_dict["context"]), dict)
        self.assertEqual(sorted(as_dict["context"].keys()), sorted(["enabled", "use_git_timestamps", "use_gitignore", "exclude", "include", "parent_dir"]))

    describe "name_spec":
        # Shared tests for image_name_spec and task_name_spec
        __only_run_tests_in_children__ = True

        @property
        def spec(self):
            raise NotImplementedError

        it "can't have whitespace":
            regex = self.spec.validators[1].regexes[0][0]
            for value in (" adsf", "d  d", "\t", " ", "d "):
                errors = [
                      BadSpecValue("Expected no whitespace", meta=self.meta, val=value)
                    , BadSpecValue("Expected value to match regex, it didn't", meta=self.meta, val=value, spec=regex)
                    ]
                with self.fuzzyAssertRaisesError(BadSpecValue, "Failed to validate", _errors=errors):
                    self.spec.normalise(self.meta, value)

        it "can only have alphanumeric, dashes and underscores and start with a letter":
            regex = self.spec.validators[1].regexes[0][0]
            for value in ("^dasdf", "kasd$", "*k", "[", "}", "<", "0", "0d"):
                errors = [BadSpecValue("Expected value to match regex, it didn't", meta=self.meta, val=value, spec=regex)]
                with self.fuzzyAssertRaisesError(BadSpecValue, "Failed to validate", _errors=errors):
                    self.spec.normalise(self.meta, value)

        it "allows values that are with alphanumeric, dashes and underscores":
            for value in ("dasdf", "ka-sd", "j_k", "l0Tk-", "d9001"):
                self.assertEqual(self.spec.normalise(self.meta, value), value)

        describe "task_name_spec":
            @property
            def spec(self):
                return HarpoonSpec().task_name_spec

    describe "task spec":
        it "creates a Task object for each task":
            tasks = HarpoonSpec().tasks_spec(["run"]).normalise(self.meta, {"one": {}})
            self.assertEqual(type(tasks), dict)
            self.assertEqual(list(tasks.keys()), ["one"])

            task = tasks["one"]
            self.assertIs(task.__class__, Task)
            self.assertEqual(task.action, "run")
            self.assertEqual(task.options, {})
            self.assertEqual(task.overrides, {})
            self.assertEqual(task.description, "Run specified task in this image")

