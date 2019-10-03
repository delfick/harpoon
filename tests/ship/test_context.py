# coding: spec

from harpoon.ship.context import ContextBuilder, ContextWrapper
from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.option_spec import image_objs as objs
from harpoon.errors import HarpoonError

from tests.helpers import HarpoonCase

from delfick_project.norms import Meta
from unittest import mock
import tarfile
import shutil
import pytest
import time
import os

describe HarpoonCase, "Context Wrapper":
    it "takes in a tarfile and tmpfile":
        t = mock.Mock(name="t")
        tmpfile = mock.Mock(name="tmpfile")
        wrapper = ContextWrapper(t, tmpfile)
        assert wrapper.t is t
        assert wrapper.tmpfile is tmpfile

    it "has a proxy to tmpfile.name":
        t = mock.Mock(name="t")
        tmpfile = mock.Mock(name="tmpfile")
        name = mock.Mock(name="mock")
        tmpfile.name = name
        assert ContextWrapper(t, tmpfile).name is name

    describe "close":
        it "closes the tarfile and seeks to the beginning of the file":
            t = mock.Mock(name="t")
            tmpfile = mock.Mock(name="tmpfile")
            wrapper = ContextWrapper(t, tmpfile)
            assert t.close.mock_calls == []
            assert tmpfile.seek.mock_calls == []

            wrapper.close()
            t.close.assert_called_once_with()
            tmpfile.seek.assert_called_once_with(0)

    describe "clone_with_new_dockerfile":
        it "copies over files from the old tar file into a new tarfile and returns a new wrapper":
            tmpfile = self.make_temp_file()
            old_tar = tarfile.open(tmpfile.name, "w")
            old_tar.add(self.make_temp_file("blah").name, "./one")
            old_tar.add(self.make_temp_file("meh").name, "./two")
            old_tar.add(self.make_temp_file("Dockerfile_lines").name, "./Dockerfile")
            wrapper = ContextWrapper(old_tar, tmpfile)

            conf = HarpoonSpec().image_spec.normalise(
                Meta({"_key_name_1": "awesome", "config_root": self.make_temp_dir()}, []),
                {"commands": ["FROM ubuntu:14.04"]},
            )
            docker_file = conf.docker_file

            with wrapper.clone_with_new_dockerfile(conf, docker_file) as new_wrapper:
                assert new_wrapper.t is not wrapper.t
                assert new_wrapper.tmpfile != wrapper.tmpfile
                new_wrapper.close()
                self.assertTarFileContent(
                    new_wrapper.t.name,
                    {"./one": "blah", "./two": "meh", "./Dockerfile": "FROM ubuntu:14.04"},
                )
                self.assertTarFileContent(
                    wrapper.t.name,
                    {"./one": "blah", "./two": "meh", "./Dockerfile": "Dockerfile_lines"},
                )

describe HarpoonCase, "Context builder":

    @pytest.fixture()
    def M(self):
        f = self.make_temp_dir()

        class Mocks:
            folder = f
            ctx = objs.Context(enabled=True, parent_dir=f)
            one_val = self.unique_val()
            two_val = self.unique_val()
            three_val = self.unique_val()
            four_val = self.unique_val()
            five_val = self.unique_val()
            find_notignored_git_files = mock.Mock(name="find_notignored_git_files")

        return Mocks

    describe "make_context":
        it "adds everything from find_files_for_tar", M:
            folder, files = self.setup_directory(
                {"one": {"1": M.one_val}, "two": M.two_val}, root=M.folder
            )

            find_files_for_tar = mock.Mock(name="find_files_for_tar")
            find_files_for_tar.return_value = [
                (files["one"]["/folder/"], "./one"),
                (files["one"]["1"]["/file/"], "./one/1"),
                (files["two"]["/file/"], "./two"),
            ]

            with mock.patch.object(ContextBuilder, "find_files_for_tar", find_files_for_tar):
                with ContextBuilder().make_context(M.ctx) as tmpfile:
                    tmpfile.close()
                    self.assertTarFileContent(
                        tmpfile.name, {"./one": None, "./one/1": M.one_val, "./two": M.two_val}
                    )

        it "adds extra_content after find_files_for_tar", M:
            find_files_for_tar = mock.Mock(name="find_files_for_tar")
            extra_context = [(M.three_val, "./one"), (M.four_val, "./four")]

            folder, files = self.setup_directory(
                {"one": M.one_val, "two": M.two_val}, root=M.folder
            )
            find_files_for_tar.return_value = [
                (files["one"]["/file/"], "./one"),
                (files["two"]["/file/"], "./two"),
            ]

            with mock.patch.object(ContextBuilder, "find_files_for_tar", find_files_for_tar):
                with ContextBuilder().make_context(M.ctx, extra_context=extra_context) as tmpfile:
                    tmpfile.close()
                    self.assertTarFileContent(
                        tmpfile.name,
                        {"./one": M.three_val, "./two": M.two_val, "./four": M.four_val},
                    )

    describe "find_files":
        it "returns all the files if not using git", M:
            _, files = self.setup_directory(
                {
                    ".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}},
                    "one": M.one_val,
                    "two": M.two_val,
                    "three": {"four": M.four_val},
                },
                root=M.folder,
            )

            expected_files = sorted(
                [
                    files[".git"]["info"]["exclude"]["/file/"],
                    files[".git"]["objects"]["ref"]["blah"]["/file/"],
                    files["one"]["/file/"],
                    files["two"]["/file/"],
                    files["three"]["four"]["/file/"],
                ]
            )

            found_files = ContextBuilder().find_files(M.ctx, False)
            assert found_files == expected_files

        it "ignores .git folder if use_gitignore is true", M:
            _, files = self.setup_directory(
                {
                    ".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}},
                    "one": M.one_val,
                    "two": M.two_val,
                    "three": {"four": M.four_val},
                },
                root=M.folder,
            )

            M.ctx.use_gitignore = True
            expected_files = sorted(
                [files["one"]["/file/"], files["two"]["/file/"], files["three"]["four"]["/file/"]]
            )

            M.find_notignored_git_files.return_value = set()
            with mock.patch.object(
                ContextBuilder, "find_notignored_git_files", M.find_notignored_git_files
            ):
                found_files = ContextBuilder().find_files(M.ctx, False)
                assert found_files == expected_files

        it "ignores files not specified as valid", M:
            _, files = self.setup_directory(
                {
                    ".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}},
                    "one": M.one_val,
                    "two": M.two_val,
                    "three": {"four": M.four_val},
                    "five": M.five_val,
                },
                root=M.folder,
            )

            M.ctx.use_gitignore = True
            expected_files = sorted(
                [files["two"]["/file/"], files["three"]["four"]["/file/"], files["five"]["/file/"]]
            )

            M.find_notignored_git_files.return_value = set(["two", "three/four", "five"])
            with mock.patch.object(
                ContextBuilder, "find_notignored_git_files", M.find_notignored_git_files
            ):
                found_files = ContextBuilder().find_files(M.ctx, False)
                assert found_files == expected_files

        it "excludes files matching the excluders", M:
            _, files = self.setup_directory(
                {
                    ".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}},
                    "one": M.one_val,
                    "two": M.two_val,
                    "three": {"four": M.four_val},
                },
                root=M.folder,
            )

            expected_files = sorted([files["one"]["/file/"], files["two"]["/file/"]])

            M.ctx.exclude = [".git/**", "three/four"]

            found_files = ContextBuilder().find_files(M.ctx, False)
            assert found_files == expected_files

        it "includes files after exclude is taken into account", M:
            _, files = self.setup_directory(
                {
                    ".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}},
                    "one": M.one_val,
                    "two": M.two_val,
                    "three": {"four": M.four_val},
                },
                root=M.folder,
            )

            expected_files = sorted(
                [
                    files[".git"]["info"]["exclude"]["/file/"],
                    files[".git"]["objects"]["ref"]["blah"]["/file/"],
                    files["one"]["/file/"],
                    files["two"]["/file/"],
                ]
            )

            M.ctx.exclude = [".git/**", "three/four"]
            M.ctx.include = [".git/**"]

            found_files = ContextBuilder().find_files(M.ctx, False)
            assert found_files == expected_files

    describe "Finding submodule files":
        it "is able to find files in a submodule":
            with self.cloned_submodule_example() as first_repo:
                ctxt = objs.Context(enabled=True, parent_dir=first_repo, use_gitignore=True)
                assert ContextBuilder().find_notignored_git_files(ctxt, False) == set(
                    ["b", ".gitmodules", "vendor/two/a"]
                )

    describe "find_notignored_git_files":
        it "finds the files":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True)
                assert ContextBuilder().find_notignored_git_files(ctxt, False) == (
                    set(
                        [
                            ".gitignore",
                            ".hidden",
                            "one",
                            "three/five",
                            "three/four/seven",
                            "three/four/six",
                            "two",
                            "three/.hidden2",
                        ]
                    )
                )

        it "includes modified and untracked files":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True)
                self.touch_files(
                    root_folder,
                    [
                        ("one", "blah"),
                        ("eight", "stuff"),
                        ("three/nine", "meh"),
                        ("fifty.pyc", "another"),
                    ],
                )
                assert ContextBuilder().find_notignored_git_files(ctxt, False) == (
                    set(
                        [
                            ".gitignore",
                            ".hidden",
                            "one",
                            "three/five",
                            "three/four/seven",
                            "three/four/six",
                            "two",
                            "three/.hidden2",
                            "eight",
                            "three/nine",
                        ]
                    )
                )

                self.assertExampleRepoStatus(
                    root_folder,
                    """
                    M one
                    ?? eight
                    ?? three/nine""",
                    sort_output=True,
                )

        it "returns valid files":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True)
                assert ContextBuilder().find_notignored_git_files(ctxt, False) == (
                    set(
                        [
                            ".gitignore",
                            ".hidden",
                            "one",
                            "three/five",
                            "three/four/seven",
                            "three/four/six",
                            "two",
                            "three/.hidden2",
                        ]
                    )
                )
                self.assertExampleRepoStatus(root_folder, "")
