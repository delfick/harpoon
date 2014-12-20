# coding: spec

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.errors import BadSpec, BadSpecValue
from harpoon.option_spec.task_objs import Task

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
import mock

describe HarpoonCase, "HarpoonSpec":
    before_each:
        self.meta = mock.Mock(name="meta")

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

        describe "image_name_spec":
            @property
            def spec(self):
                return HarpoonSpec().image_name_spec

        describe "task_name_spec":
            @property
            def spec(self):
                return HarpoonSpec().task_name_spec

    describe "task spec":
        it "creates a Task object for each task":
            meta_at = mock.Mock(name="meta_at", base={})
            self.meta.at.return_value = meta_at

            tasks = HarpoonSpec().tasks_spec(["run"]).normalise(self.meta, {"one": {}})
            self.assertEqual(type(tasks), dict)
            self.assertEqual(list(tasks.keys()), ["one"])

            task = tasks["one"]
            self.assertIs(task.__class__, Task)
            self.assertEqual(task.action, "run")
            self.assertEqual(task.options, {})
            self.assertEqual(task.overrides, {})
            self.assertEqual(task.description, "")

