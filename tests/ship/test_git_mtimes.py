# coding: spec

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.option_spec import image_objs as objs
from harpoon.ship.git_mtimes import GitMtimes
from harpoon.errors import HarpoonError

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
import time
import os

describe HarpoonCase, "GitMtimes":
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

        self.five_val = self.unique_val()
        self.five_mtime = int(time.time()) + 30

    describe "find":

        def find(self, context, silent_build):
            return GitMtimes(context.git_root, context.parent_dir, context.use_git_timestamps, context.include, context.exclude, silent_build).find()

        it "is able to find all the files owned by git and get their last commit modified time":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=True)
                self.assertEqual(self.find(ctxt, False), self.repo_example_map())

        it "only includes files under the parent_dir":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=True)
                expected_map = dict((key[6:], val) for key, val in self.repo_example_map().items() if key.startswith("three"))
                self.assertEqual(self.find(ctxt, False), expected_map)

        it "only includes files specified by use_git_timestamps relative to parent_dir":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=["four/**"])
                mp = self.repo_example_map()
                expected_map = {"four/seven": mp["three/four/seven"], "four/six": mp["three/four/six"]}
                self.assertEqual(self.find(ctxt, False), expected_map)

            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=["three/four/**"])
                mp = self.repo_example_map()
                expected_map = {"three/four/seven": mp["three/four/seven"], "three/four/six": mp["three/four/six"]}
                self.assertEqual(self.find(ctxt, False), expected_map)

        it "excludes files in context.exclude relative to the parent_dir":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=True, exclude=["four/**"])
                mp = self.repo_example_map()
                expected_map = {".hidden2": mp["three/.hidden2"], "five": mp["three/five"]}
                self.assertEqual(self.find(ctxt, False), expected_map)

            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=True, exclude=["three/four/**", "symlinkd"])
                mp = self.repo_example_map()
                expected_map = {"three/.hidden2": mp["three/.hidden2"], "three/five": mp["three/five"], "one": mp["one"], "two": mp["two"], ".gitignore": mp[".gitignore"], ".hidden": mp[".hidden"]}
                self.assertEqual(self.find(ctxt, False), expected_map)

        it "includes files in context.include after context.exclude":
            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=os.path.join(root_folder, "three"), use_gitignore=True, use_git_timestamps=True, exclude=["four/**", "symlinkd"], include=["four/seven"])
                mp = self.repo_example_map()
                expected_map = {".hidden2": mp["three/.hidden2"], "five": mp["three/five"], "four/seven": mp["three/four/seven"]}
                self.assertEqual(self.find(ctxt, False), expected_map)

            with self.cloned_repo_example() as root_folder:
                ctxt = objs.Context(enabled=True, parent_dir=root_folder, use_gitignore=True, use_git_timestamps=True, exclude=["three/four/**", "symlinkd"], include=["three/four/seven"])
                mp = self.repo_example_map()
                expected_map = {"three/.hidden2": mp["three/.hidden2"], "three/five": mp["three/five"], "one": mp["one"], "two": mp["two"], ".gitignore": mp[".gitignore"], "three/four/seven": mp["three/four/seven"], ".hidden": mp[".hidden"]}
                self.assertEqual(self.find(ctxt, False), expected_map)

