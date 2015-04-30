# coding: spec

from harpoon.ship.context import ContextBuilder, ContextWrapper
from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.option_spec import image_objs as objs
from harpoon.errors import HarpoonError

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
from input_algorithms.meta import Meta
import tarfile
import shutil
import time
import nose
import mock
import six
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
            if six.PY3:
                raise nose.SkipTest()

            tmpfile = self.make_temp_file()
            old_tar = tarfile.open(tmpfile.name, "w:gz")
            old_tar.add(self.make_temp_file("blah").name, "./one")
            old_tar.add(self.make_temp_file("meh").name, "./two")
            old_tar.add(self.make_temp_file("Dockerfile_lines").name, "./Dockerfile")
            wrapper = ContextWrapper(old_tar, tmpfile)
            wrapper.close()

            conf = HarpoonSpec().image_spec.normalise(
                  Meta({"_key_name_1": "awesome", "config_root": self.make_temp_dir()}, [])
                , {"commands": ["FROM ubuntu:14.04"]}
                )
            docker_file = conf.docker_file

            with wrapper.clone_with_new_dockerfile(conf, docker_file) as new_wrapper:
                assert new_wrapper.t is not wrapper.t
                self.assertNotEqual(new_wrapper.tmpfile, wrapper.tmpfile)
                new_wrapper.close()
                self.assertTarFileContent(new_wrapper.t.name, {"./one": "blah", "./two": "meh", "./Dockerfile": "FROM ubuntu:14.04"})
                self.assertTarFileContent(wrapper.t.name, {"./one": "blah", "./two": "meh", "./Dockerfile": "Dockerfile_lines"})

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

        it "adds everything from find_mtimes":
            find_mtimes = mock.Mock(name="find_mtimes")
            mtime = int(time.time())
            folder, files = self.setup_directory({"one": {"1": self.one_val}, "two": self.two_val}, root=self.folder)
            find_mtimes.return_value = [(files["one"]["/folder/"], mtime, './one'), (files["one"]["1"]["/file/"], mtime, "./one/1"), (files["two"]["/file/"], mtime, "./two")]

            with mock.patch.object(ContextBuilder, "find_mtimes", find_mtimes):
                with ContextBuilder().make_context(self.context) as tmpfile:
                    tmpfile.close()
                    self.assertTarFileContent(tmpfile.name
                        , {"./one": (mtime, None), "./one/1": (mtime, self.one_val), "./two": (mtime, self.two_val)}
                        )

        it "adds extra_content after find_mtimes":
            find_mtimes = mock.Mock(name="find_mtimes")
            extra_context = [(self.three_val, "./one"), (self.four_val, "./four")]

            mtime = int(time.time())
            folder, files = self.setup_directory({"one": self.one_val, "two": self.two_val}, root=self.folder)
            find_mtimes.return_value = [(files["one"]["/file/"], mtime, './one'), (files["two"]["/file/"], mtime, "./two")]

            with mock.patch.object(ContextBuilder, "find_mtimes", find_mtimes):
                with ContextBuilder().make_context(self.context, extra_context=extra_context) as tmpfile:
                    tmpfile.close()
                    self.assertTarFileContent(tmpfile.name
                        , {"./one": (mtime, self.three_val), "./two": (mtime, self.two_val), "./four": (self.mtime, self.four_val)}
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
                  files[".git"]["info"]["exclude"]["/file/"], files[".git"]["objects"]["ref"]["blah"]["/file/"]
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

            self.find_ignored_git_files.return_value = (set(), set(), set())
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

            self.find_ignored_git_files.return_value = (set(), set(), set(["one"]))
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
                  files[".git"]["info"]["exclude"]["/file/"]
                , files[".git"]["objects"]["ref"]["blah"]["/file/"]
                , files["one"]["/file/"], files["two"]["/file/"], files["three"]["four"]["/file/"]
                ])

            self.find_ignored_git_files.return_value = (set(), set(), set())
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
                  files[".git"]["info"]["exclude"]["/file/"]
                , files[".git"]["objects"]["ref"]["blah"]["/file/"]
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
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=True)
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), self.repo_example_map())

        it "complains if the git repo is a shallow clone":
            with self.cloned_repo_example(shallow=True) as root_folder:
                with self.fuzzyAssertRaisesError(HarpoonError, "Can't get git timestamps from a shallow clone", directory=root_folder):
                    ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=True)
                    ContextBuilder().find_git_mtimes(ctxt, False)

        it "only includes files under the parent_dir":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=True)
                expected_map = dict((key[6:], val) for key, val in self.repo_example_map().items() if key.startswith("three"))
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

        it "only includes files specified by use_git_timestamps relative to parent_dir":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=["four/**"])
                mp = self.repo_example_map()
                expected_map = {"four/seven": mp["three/four/seven"], "four/six": mp["three/four/six"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=["three/four/**"])
                mp = self.repo_example_map()
                expected_map = {"three/four/seven": mp["three/four/seven"], "three/four/six": mp["three/four/six"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

        it "excludes files in context.exclude relative to the parent_dir":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=True, exclude=["four/**"])
                mp = self.repo_example_map()
                expected_map = {".hidden2": mp["three/.hidden2"], "five": mp["three/five"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=True, exclude=["three/four/**"])
                mp = self.repo_example_map()
                expected_map = {"three/.hidden2": mp["three/.hidden2"], "three/five": mp["three/five"], "one": mp["one"], "two": mp["two"], ".gitignore": mp[".gitignore"], ".hidden": mp[".hidden"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

        it "includes files in context.include after context.exclude":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=True, exclude=["four/**"], include=["four/seven"])
                mp = self.repo_example_map()
                expected_map = {".hidden2": mp["three/.hidden2"], "five": mp["three/five"], "four/seven": mp["three/four/seven"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=True, exclude=["three/four/**"], include=["three/four/seven"])
                mp = self.repo_example_map()
                expected_map = {"three/.hidden2": mp["three/.hidden2"], "three/five": mp["three/five"], "one": mp["one"], "two": mp["two"], ".gitignore": mp[".gitignore"], "three/four/seven": mp["three/four/seven"], ".hidden": mp[".hidden"]}
                self.assertEqual(ContextBuilder().find_git_mtimes(ctxt, False), expected_map)

    describe "find_ignored_git_files":
        it "returns empty on a new clone":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder)
                self.assertEqual(ContextBuilder().find_ignored_git_files(ctxt, False), (set(), set(), set()))

            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_git_timestamps=True, use_gitignore=True)
                self.assertEqual(ContextBuilder().find_ignored_git_files(ctxt, False), (set(), set(), set()))

        it "returns the changed and untracked files as mtime_ignoreable":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True)
                self.touch_files(root_folder, [("one", "blah"), ("eight", "stuff"), ("three/nine", "meh"), ("fifty.pyc", "another")])
                self.assertEqual(ContextBuilder().find_ignored_git_files(ctxt, False), (set(["one"]), set(["eight", "three/nine"]), set(["fifty.pyc"])))
                self.assertExampleRepoStatus(root_folder, """
                    M one
                    ?? eight
                    ?? three/nine
                """)

        it "returns ignored files in ignored":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True)
                self.touch_files(root_folder, [("one.pyc", "")])
                self.assertEqual(ContextBuilder().find_ignored_git_files(ctxt, False), (set(), set(), set(["one.pyc"])))
                self.assertExampleRepoStatus(root_folder, "")

        it "doesn't return ignored files in ignored if not use_gitignore":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=False)
                self.touch_files(root_folder, [("one.pyc", "")])
                self.assertEqual(ContextBuilder().find_ignored_git_files(ctxt, False), (set(), set(), set()))
                self.assertExampleRepoStatus(root_folder, "")

