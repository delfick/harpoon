# coding: spec

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.errors import BadSpec, BadSpecValue
from harpoon.option_spec.task_objs import Task

from tests.helpers import HarpoonCase

from delfick_project.errors_pytest import assertRaises
from delfick_project.option_merge import MergedOptions
from delfick_project.norms import Meta
from unittest import mock
import pytest

describe HarpoonCase, "HarpoonSpec":

    @pytest.fixture()
    def meta(self):
        docker_context = mock.Mock(name="docker_context")
        harpoon = mock.Mock(name="harpoon", docker_context=docker_context)
        return Meta({"harpoon": harpoon}, [])

    it "can get a fake Image":
        with self.a_temp_dir() as directory:
            harpoon = mock.Mock(name="harpoon")
            everything = MergedOptions.using(
                {"config_root": directory, "_key_name_1": "blah", "harpoon": harpoon}
            )
            meta = Meta(everything, [])
            fake = HarpoonSpec().image_spec.fake_filled(meta, with_non_defaulted=True)
            assert fake.context.parent_dir == directory
            assert fake.name == "blah"

        as_dict = fake.as_dict()
        assert type(as_dict["context"]) == dict
        assert sorted(as_dict["context"].keys()) == (
            sorted(
                [
                    "enabled",
                    "use_gitignore",
                    "exclude",
                    "include",
                    "parent_dir",
                    "find_options",
                    "ignore_find_errors",
                ]
            )
        )

    describe "name_spec":
        # Shared tests for image_name_spec and task_name_spec
        __only_run_tests_in_children__ = True

        @property
        def spec(self):
            raise NotImplementedError

        it "can't have whitespace", meta:
            regex = self.spec.validators[1].regexes[0][0]
            for value in (" adsf", "d  d", "\t", " ", "d "):
                errors = [
                    BadSpecValue("Expected no whitespace", meta=meta, val=value),
                    BadSpecValue(
                        "Expected value to match regex, it didn't", meta=meta, val=value, spec=regex
                    ),
                ]
                with assertRaises(BadSpecValue, "Failed to validate", _errors=errors):
                    self.spec.normalise(meta, value)

        it "can only have alphanumeric, dashes and underscores and start with a letter", meta:
            regex = self.spec.validators[1].regexes[0][0]
            for value in ("^dasdf", "kasd$", "*k", "[", "}", "<", "0", "0d"):
                errors = [
                    BadSpecValue(
                        "Expected value to match regex, it didn't", meta=meta, val=value, spec=regex
                    )
                ]
                with assertRaises(BadSpecValue, "Failed to validate", _errors=errors):
                    self.spec.normalise(meta, value)

        it "allows values that are with alphanumeric, dashes and underscores", meta:
            for value in ("dasdf", "ka-sd", "j_k", "l0Tk-", "d9001"):
                assert self.spec.normalise(meta, value) == value

        describe "task_name_spec":

            @property
            def spec(self):
                return HarpoonSpec().task_name_spec

    describe "task spec":
        it "creates a Task object for each task", meta:
            tasks = HarpoonSpec().tasks_spec(["run"]).normalise(meta, {"one": {}})
            assert type(tasks) == dict
            assert list(tasks.keys()) == ["one"]

            task = tasks["one"]
            assert task.__class__ is Task
            assert task.action == "run"
            assert task.options == {}
            assert task.overrides == {}
            assert task.description == "Run specified task in this image"
