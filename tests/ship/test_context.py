# coding: spec

from harpoon.option_spec import image_objs as objs
from harpoon.ship.context import ContextBuilder
from harpoon.errors import HarpoonError

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
import shutil
import time
import nose
import mock
import six
import os

describe HarpoonCase, "Context builder":
    before_each:
        self.folder = self.make_temp_dir()
        self.context = objs.Context(enabled=True, parent_dir=self.folder)

        self.one_val = self.unique_val()
        self.one_mtime = int(time.time())

        self.two_val = self.unique_val()
        self.two_mtime = int(time.time()) + 10

        self.three_val = self.unique_val()
        self.three_mtime = int(time.time()) + 11

        self.four_val = self.unique_val()
        self.four_mtime = int(time.time()) + 20

    describe "make_context":
        before_each:
            self.mtime = int(time.time())
            self.docker_lines = '\n'.join(["FROM somewhere", "RUN touch /tmp/stuff"])
            self.docker_file = objs.DockerFile(self.docker_lines, self.mtime)

        it "adds Dockerfile and everything from find_mtimes":
            find_mtimes = mock.Mock(name="find_mtimes")
            mtime = int(time.time())
            folder, files = self.setup_directory({"one": {"1": self.one_val}, "two": self.two_val}, root=self.folder)
            find_mtimes.return_value = [(files["one"]["/folder/"], mtime, './one'), (files["one"]["1"]["/file/"], mtime, "./one/1"), (files["two"]["/file/"], mtime, "./two")]

            with mock.patch.object(ContextBuilder, "find_mtimes", find_mtimes):
                with ContextBuilder().make_context(self.context, self.docker_file) as tmpfile:
                    self.assertTarFileContent(tmpfile.name
                        , {"./one": (mtime, None), "./one/1": (mtime, self.one_val), "./two": (mtime, self.two_val), "./Dockerfile": (self.mtime, self.docker_lines)}
                        )

        it "adds extra_content after find_mtimes":
            find_mtimes = mock.Mock(name="find_mtimes")
            extra_context = [(self.three_val, "./one"), (self.four_val, "./four")]

            mtime = int(time.time())
            folder, files = self.setup_directory({"one": self.one_val, "two": self.two_val}, root=self.folder)
            find_mtimes.return_value = [(files["one"]["/file/"], mtime, './one'), (files["two"]["/file/"], mtime, "./two")]

            with mock.patch.object(ContextBuilder, "find_mtimes", find_mtimes):
                with ContextBuilder().make_context(self.context, self.docker_file, extra_context=extra_context) as tmpfile:
                    self.assertTarFileContent(tmpfile.name
                        , {"./one": (mtime, self.three_val), "./two": (mtime, self.two_val), "./four": (self.mtime, self.four_val), "./Dockerfile": (self.mtime, self.docker_lines)}
                        )

    describe "find_mtimes":
        before_each:
            self.find_git_mtimes = mock.Mock(name="find_git_mtimes")
            self.find_files = mock.Mock(name="find_files")

        it "uses methods on ContextBuilder to find files and mtimes to yield":
            one_path = os.path.join(self.folder, "one", "1")
            two_path = os.path.join(self.folder, "two", "three", "four")

            self.find_git_mtimes.return_value = {"one/1": self.one_mtime, "two/three/four": self.two_mtime}
            self.find_files.return_value = [one_path, two_path], []

            # Make sure the files exist
            self.setup_directory({"one": {"1": ""}, "two": {"three": {"four": ""}}}, root=self.folder)

            with mock.patch.multiple(ContextBuilder, find_git_mtimes=self.find_git_mtimes, find_files=self.find_files):
                self.context.use_git_timestamps = True
                result = list(ContextBuilder().find_mtimes(self.context, False))
                self.assertEqual(result
                    , [(one_path, self.one_mtime, "./one/1"), (two_path, self.two_mtime, "./two/three/four")]
                    )

        it "ignores files that don't exist":
            one_path = os.path.join(self.folder, "one", "1")
            two_path = os.path.join(self.folder, "two", "three", "four")

            self.find_git_mtimes.return_value = {"one/1": self.one_mtime, "two/three/four": self.two_mtime}
            self.find_files.return_value = [one_path, two_path], []

            # Make sure the files exist
            _, files = self.setup_directory({"one": {"1": ""}, "two": {"three": {"four": ""}}}, root=self.folder)

            # Remove the two folder
            shutil.rmtree(files["two"]["/folder/"])

            with mock.patch.multiple(ContextBuilder, find_git_mtimes=self.find_git_mtimes, find_files=self.find_files):
                self.context.use_git_timestamps = True
                result = list(ContextBuilder().find_mtimes(self.context, False))
                self.assertEqual(result
                    , [(one_path, self.one_mtime, "./one/1")]
                    )

        it "ignores mtimes if use_gitignore is False":
            one_path = os.path.join(self.folder, "one", "1")
            two_path = os.path.join(self.folder, "two", "three", "four")

            self.find_git_mtimes.return_value = {"one/1": self.one_mtime, "two/three/four": self.two_mtime}
            self.find_files.return_value = [one_path, two_path], []

            # Make sure the files exist
            self.setup_directory({"one": {"1": ""}, "two": {"three": {"four": ""}}}, root=self.folder)

            with mock.patch.multiple(ContextBuilder, find_git_mtimes=self.find_git_mtimes, find_files=self.find_files):
                self.context.use_git_timestamps = False
                result = list(ContextBuilder().find_mtimes(self.context, False))
                self.assertEqual(result
                    , [(one_path, None, "./one/1"), (two_path, None, "./two/three/four")]
                    )

        it "ignores mtime when relpath not in the mtime":
            one_path = os.path.join(self.folder, "one", "1")
            two_path = os.path.join(self.folder, "two", "three", "four")

            self.find_git_mtimes.return_value = {"one/1": self.one_mtime}
            self.find_files.return_value = [one_path, two_path], []

            # Make sure the files exist
            self.setup_directory({"one": {"1": ""}, "two": {"three": {"four": ""}}}, root=self.folder)

            with mock.patch.multiple(ContextBuilder, find_git_mtimes=self.find_git_mtimes, find_files=self.find_files):
                self.context.use_git_timestamps = True
                result = list(ContextBuilder().find_mtimes(self.context, False))
                self.assertEqual(result
                    , [(one_path, self.one_mtime, "./one/1"), (two_path, None, "./two/three/four")]
                    )

        it "ignores mtimes if relpath in mtime_ignoreable":
            one_path = os.path.join(self.folder, "one", "1")
            two_path = os.path.join(self.folder, "two", "three", "four")

            self.find_git_mtimes.return_value = {"one/1": self.one_mtime, "two/three/four": self.two_mtime}
            self.find_files.return_value = [one_path, two_path], ["two/three/four"]

            # Make sure the files exist
            self.setup_directory({"one": {"1": ""}, "two": {"three": {"four": ""}}}, root=self.folder)

            with mock.patch.multiple(ContextBuilder, find_git_mtimes=self.find_git_mtimes, find_files=self.find_files):
                self.context.use_git_timestamps = True
                result = list(ContextBuilder().find_mtimes(self.context, False))
                self.assertEqual(result
                    , [(one_path, self.one_mtime, "./one/1"), (two_path, None, "./two/three/four")]
                    )

    describe "find_files":
        before_each:
            self.find_ignored_git_files = mock.Mock(name="find_ignored_git_files")

        it "returns all the files if not using git":
            _, files = self.setup_directory(
                  {".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}}, "one": self.one_val, "two": self.two_val, "three": {"four": self.four_val}}
                , root=self.folder
                )

            assert not self.context.use_git
            expected_files = sorted([
                  files[".git"]["info"]["/folder/"]
                , files[".git"]["info"]["exclude"]["/file/"], files[".git"]["objects"]["/folder/"]
                , files[".git"]["objects"]["ref"]["/folder/"], files[".git"]["objects"]["ref"]["blah"]["/file/"]
                , files["one"]["/file/"], files["two"]["/file/"], files["three"]["four"]["/file/"]
                ])

            found_files, found_mtime_ignoreable = ContextBuilder().find_files(self.context, False)
            self.assertEqual(found_files, expected_files)
            self.assertEqual(found_mtime_ignoreable, set())

        it "ignores .git folder if use_gitignore is true":
            _, files = self.setup_directory(
                  {".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}}, "one": self.one_val, "two": self.two_val, "three": {"four": self.four_val}}
                , root=self.folder
                )

            self.context.use_gitignore = True
            assert self.context.use_git
            expected_files = sorted([
                  files["one"]["/file/"], files["two"]["/file/"], files["three"]["four"]["/file/"]
                ])

            self.find_ignored_git_files.return_value = (set(), set())
            with mock.patch.object(ContextBuilder, "find_ignored_git_files", self.find_ignored_git_files):
                found_files, found_mtime_ignoreable = ContextBuilder().find_files(self.context, False)
                self.assertEqual(found_files, expected_files)
                self.assertEqual(found_mtime_ignoreable, set())

        it "ignores files specified as ignored":
            _, files = self.setup_directory(
                  {".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}}, "one": self.one_val, "two": self.two_val, "three": {"four": self.four_val}}
                , root=self.folder
                )

            self.context.use_gitignore = True
            assert self.context.use_git
            expected_files = sorted([
                  files["two"]["/file/"], files["three"]["four"]["/file/"]
                ])

            self.find_ignored_git_files.return_value = (set(), set(["one"]))
            with mock.patch.object(ContextBuilder, "find_ignored_git_files", self.find_ignored_git_files):
                found_files, found_mtime_ignoreable = ContextBuilder().find_files(self.context, False)
                self.assertEqual(found_files, expected_files)
                self.assertEqual(found_mtime_ignoreable, set())

        it "includes ignored files if use_git is True but use_gitignore is False":
            _, files = self.setup_directory(
                  {".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}}, "one": self.one_val, "two": self.two_val, "three": {"four": self.four_val}}
                , root=self.folder
                )

            self.context.use_git_timestamps = True
            assert self.context.use_git
            assert not self.context.use_gitignore
            expected_files = sorted([
                  files[".git"]["info"]["/folder/"]
                , files[".git"]["info"]["exclude"]["/file/"], files[".git"]["objects"]["/folder/"]
                , files[".git"]["objects"]["ref"]["/folder/"], files[".git"]["objects"]["ref"]["blah"]["/file/"]
                , files["one"]["/file/"], files["two"]["/file/"], files["three"]["four"]["/file/"]
                ])

            self.find_ignored_git_files.return_value = (set(), set())
            with mock.patch.object(ContextBuilder, "find_ignored_git_files", self.find_ignored_git_files):
                found_files, found_mtime_ignoreable = ContextBuilder().find_files(self.context, False)
                self.assertEqual(found_files, expected_files)
                self.assertEqual(found_mtime_ignoreable, set())

        it "excludes files matching the excluders":
            _, files = self.setup_directory(
                  {".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}}, "one": self.one_val, "two": self.two_val, "three": {"four": self.four_val}}
                , root=self.folder
                )

            assert not self.context.use_git
            expected_files = sorted([
                  files["one"]["/file/"], files["two"]["/file/"]
                ])

            self.context.exclude = [".git/**", "three/four"]

            found_files, found_mtime_ignoreable = ContextBuilder().find_files(self.context, False)
            self.assertEqual(found_files, expected_files)
            self.assertEqual(found_mtime_ignoreable, set())

        it "includes files after exclude is taken into account":
            _, files = self.setup_directory(
                  {".git": {"info": {"exclude": ""}, "objects": {"ref": {"blah": ""}}}, "one": self.one_val, "two": self.two_val, "three": {"four": self.four_val}}
                , root=self.folder
                )

            assert not self.context.use_git
            expected_files = sorted([
                  files[".git"]["info"]["/folder/"]
                , files[".git"]["info"]["exclude"]["/file/"], files[".git"]["objects"]["/folder/"]
                , files[".git"]["objects"]["ref"]["/folder/"], files[".git"]["objects"]["ref"]["blah"]["/file/"]
                , files["one"]["/file/"], files["two"]["/file/"]
                ])

            self.context.exclude = [".git/**", "three/four"]
            self.context.include = [".git/**"]

            found_files, found_mtime_ignoreable = ContextBuilder().find_files(self.context, False)
            self.assertEqual(found_files, expected_files)
            self.assertEqual(found_mtime_ignoreable, set())

    describe "find_git_mtimes":
        before_each:
            # Dulwich doesn't seem to work well in python3
            # That work seems to be ongoing, will re-enable these tests in the future
            if six.PY3:
                raise nose.SkipTest()

        it "is able to find all the files owned by git and get their last commit modified time":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=True)
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), self.repo_example_map())

        it "complains if the git repo is a shallow clone":
            with self.cloned_repo_example(shallow=True) as root_folder:
                with self.fuzzyAssertRaisesError(HarpoonError, "Can't get git timestamps from a shallow clone", directory=root_folder):
                    ctxt = objs.Context(True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=True)
                    ContextBuilder().find_git_mtimes(ctxt, False)

        it "only includes files under the parent_dir":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=True)
                expected_map = dict((key, val) for key, val in self.repo_example_map().items() if key.startswith("three"))
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

        it "only includes files specified by use_git_timestamps relative to parent_dir":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=["four/**"])
                mp = self.repo_example_map()
                expected_map = {"three/four/seven": mp["three/four/seven"], "three/four/six": mp["three/four/six"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=["three/four/**"])
                mp = self.repo_example_map()
                expected_map = {"three/four/seven": mp["three/four/seven"], "three/four/six": mp["three/four/six"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

        it "excludes files in context.exclude relative to the parent_dir":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=True, exclude=["four/**"])
                mp = self.repo_example_map()
                expected_map = {"three/five": mp["three/five"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=True, exclude=["three/four/**"])
                mp = self.repo_example_map()
                expected_map = {"three/five": mp["three/five"], "one": mp["one"], "two": mp["two"], ".gitignore": mp[".gitignore"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

        it "includes files in context.include after context.exclude":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=True, exclude=["four/**"], include=["four/seven"])
                mp = self.repo_example_map()
                expected_map = {"three/five": mp["three/five"], "three/four/seven": mp["three/four/seven"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=True, exclude=["three/four/**"], include=["three/four/seven"])
                mp = self.repo_example_map()
                expected_map = {"three/five": mp["three/five"], "one": mp["one"], "two": mp["two"], ".gitignore": mp[".gitignore"], "three/four/seven": mp["three/four/seven"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

    describe "find_ignored_git_files":
        it "returns empty on a new clone":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=root_folder)
                self.assertEqual(ContextBuilder().find_ignored_git_files(ctxt, False), (set(), set()))

            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=root_folder, use_git_timestamps=True, use_gitignore=True)
                self.assertEqual(ContextBuilder().find_ignored_git_files(ctxt, False), (set(), set()))

        it "returns the changed and untracked files as mtime_ignoreable":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=root_folder)
                self.touch_files(root_folder, [("one", "blah"), ("eight", "stuff"), ("three/nine", "meh")])
                self.assertEqual(ContextBuilder().find_ignored_git_files(ctxt, False), (set(["one", "eight", "three/nine"]), set()))
                self.assertExampleRepoStatus(root_folder, """
                    M one
                    ?? eight
                    ?? three/nine
                """)

        it "returns ignored files in ignored":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=root_folder, use_gitignore=True)
                self.touch_files(root_folder, [("one.pyc", "")])
                self.assertEqual(ContextBuilder().find_ignored_git_files(ctxt, False), (set(), set(["one.pyc"])))
                self.assertExampleRepoStatus(root_folder, "")

        it "doesn't return ignored files in ignored if not use_gitignore":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(True, parent_dir=root_folder, use_gitignore=False)
                self.touch_files(root_folder, [("one.pyc", "")])
                self.assertEqual(ContextBuilder().find_ignored_git_files(ctxt, False), (set(), set()))
                self.assertExampleRepoStatus(root_folder, "")

