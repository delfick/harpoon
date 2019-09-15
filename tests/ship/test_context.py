# coding: spec

from harpoon.ship.context import ContextBuilder, ContextWrapper
from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.option_spec import image_objs as objs
from harpoon.errors import HarpoonError

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
from delfick_project.norms import Meta
import tarfile
import shutil
import time
import nose
import mock
import os

describe HarpoonCase, "Context Wrapper":
    before_each:
        self.t = mock.Mock(name="t")
        self.tmpfile = mock.Mock(name="tmpfile")

    it "takes in a tarfile and tmpfile":
        wrapper = ContextWrapper(self.t, self.tmpfile)
        self.assertIs(wrapper.t, self.t)
        self.assertIs(wrapper.tmpfile, self.tmpfile)

    it "has a proxy to tmpfile.name":
        name = mock.Mock(name="mock")
        self.tmpfile.name = name
        self.assertIs(ContextWrapper(self.t, self.tmpfile).name, name)

    describe "close":
        it "closes the tarfile and seeks to the beginning of the file":
            wrapper = ContextWrapper(self.t, self.tmpfile)
            self.assertEqual(self.t.close.mock_calls, [])
            self.assertEqual(self.tmpfile.seek.mock_calls, [])

            wrapper.close()
            self.t.close.assert_called_once()
            self.tmpfile.seek.assert_called_once_with(0)

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
                self.assertNotEqual(new_wrapper.tmpfile, wrapper.tmpfile)
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
    before_each:
        self.folder = self.make_temp_dir()
        self.context = objs.Context(enabled=True, parent_dir=self.folder)

        self.one_val = self.unique_val()
        self.two_val = self.unique_val()
        self.three_val = self.unique_val()
        self.four_val = self.unique_val()
        self.five_val = self.unique_val()

    describe "make_context":
        before_each:
            self.docker_lines = "\n".join(["FROM somewhere", "RUN touch /tmp/stuff"])
            self.docker_file = objs.DockerFile(self.docker_lines)

        it "adds everything from find_files_for_tar":
            folder, files = self.setup_directory(
                {"one": {"1": self.one_val}, "two": self.two_val}, root=self.folder
            )

            find_files_for_tar = mock.Mock(name="find_files_for_tar")
            find_files_for_tar.return_value = [
                (files["one"]["/folder/"], "./one"),
                (files["one"]["1"]["/file/"], "./one/1"),
                (files["two"]["/file/"], "./two"),
            ]

            with mock.patch.object(ContextBuilder, "find_files_for_tar", find_files_for_tar):
                with ContextBuilder().make_context(self.context) as tmpfile:
                    tmpfile.close()
                    self.assertTarFileContent(
                        tmpfile.name,
                        {"./one": None, "./one/1": self.one_val, "./two": self.two_val},
                    )

        it "adds extra_content after find_files_for_tar":
            find_files_for_tar = mock.Mock(name="find_files_for_tar")
            extra_context = [(self.three_val, "./one"), (self.four_val, "./four")]

            folder, files = self.setup_directory(
                {"one": self.one_val, "two": self.two_val}, root=self.folder
            )
            find_files_for_tar.return_value = [
                (files["one"]["/file/"], "./one"),
                (files["two"]["/file/"], "./two"),
            ]

            with mock.patch.object(ContextBuilder, "find_files_for_tar", find_files_for_tar):
                with ContextBuilder().make_context(
                    self.context, extra_context=extra_context
                ) as tmpfile:
                    tmpfile.close()
                    self.assertTarFileContent(
                        tmpfile.name,
                        {"./one": self.three_val, "./two": self.two_val, "./four": self.four_val},
                    )

    describe "find_files":
        before_each:
            self.find_notignored_git_files = mock.Mock(name="find_notignored_git_files")

        it "returns all the files if not using git":
            _, files = self.setup_directory(
                {
                    ".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}},
                    "one": self.one_val,
                    "two": self.two_val,
                    "three": {"four": self.four_val},
                },
                root=self.folder,
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

            found_files = ContextBuilder().find_files(self.context, False)
            self.assertEqual(found_files, expected_files)

        it "ignores .git folder if use_gitignore is true":
            _, files = self.setup_directory(
                {
                    ".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}},
                    "one": self.one_val,
                    "two": self.two_val,
                    "three": {"four": self.four_val},
                },
                root=self.folder,
            )

            self.context.use_gitignore = True
            expected_files = sorted(
                [files["one"]["/file/"], files["two"]["/file/"], files["three"]["four"]["/file/"]]
            )

            self.find_notignored_git_files.return_value = set()
            with mock.patch.object(
                ContextBuilder, "find_notignored_git_files", self.find_notignored_git_files
            ):
                found_files = ContextBuilder().find_files(self.context, False)
                self.assertEqual(found_files, expected_files)

        it "ignores files not specified as valid":
            _, files = self.setup_directory(
                {
                    ".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}},
                    "one": self.one_val,
                    "two": self.two_val,
                    "three": {"four": self.four_val},
                    "five": self.five_val,
                },
                root=self.folder,
            )

            self.context.use_gitignore = True
            expected_files = sorted(
                [files["two"]["/file/"], files["three"]["four"]["/file/"], files["five"]["/file/"]]
            )

            self.find_notignored_git_files.return_value = set(["two", "three/four", "five"])
            with mock.patch.object(
                ContextBuilder, "find_notignored_git_files", self.find_notignored_git_files
            ):
                found_files = ContextBuilder().find_files(self.context, False)
                self.assertEqual(found_files, expected_files)

        it "excludes files matching the excluders":
            _, files = self.setup_directory(
                {
                    ".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}},
                    "one": self.one_val,
                    "two": self.two_val,
                    "three": {"four": self.four_val},
                },
                root=self.folder,
            )

            expected_files = sorted([files["one"]["/file/"], files["two"]["/file/"]])

            self.context.exclude = [".git/**", "three/four"]

            found_files = ContextBuilder().find_files(self.context, False)
            self.assertEqual(found_files, expected_files)

        it "includes files after exclude is taken into account":
            _, files = self.setup_directory(
                {
                    ".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}},
                    "one": self.one_val,
                    "two": self.two_val,
                    "three": {"four": self.four_val},
                },
                root=self.folder,
            )

            expected_files = sorted(
                [
                    files[".git"]["info"]["exclude"]["/file/"],
                    files[".git"]["objects"]["ref"]["blah"]["/file/"],
                    files["one"]["/file/"],
                    files["two"]["/file/"],
                ]
            )

            self.context.exclude = [".git/**", "three/four"]
            self.context.include = [".git/**"]

            found_files = ContextBuilder().find_files(self.context, False)
            self.assertEqual(found_files, expected_files)

    describe "Finding submodule files":
        it "is able to find files in a submodule":
            with self.cloned_submodule_example() as first_repo:
                ctxt = objs.Context(enabled=True, parent_dir=first_repo, use_gitignore=True)
                self.assertEqual(
                    ContextBuilder().find_notignored_git_files(ctxt, False),
                    set(["b", ".gitmodules", "vendor/two/a"]),
                )

    describe "find_notignored_git_files":
        it "finds the files":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True)
                self.assertEqual(
                    ContextBuilder().find_notignored_git_files(ctxt, False),
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
                    ),
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
                self.assertEqual(
                    ContextBuilder().find_notignored_git_files(ctxt, False),
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
                    ),
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
                self.assertEqual(
                    ContextBuilder().find_notignored_git_files(ctxt, False),
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
                    ),
                )
                self.assertExampleRepoStatus(root_folder, "")
