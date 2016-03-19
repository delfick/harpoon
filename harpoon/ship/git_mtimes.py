"""
Class for getting the commit modified times of files from git

Also responsible for saving and loading a file cache of those modified times
"""

from harpoon.errors import HarpoonError

from collections import namedtuple
from dulwich.repo import Repo
import fnmatch
import logging
import json
import os

log = logging.getLogger("harpoon.ship.git_mtimes")

Path = namedtuple("Path", ["path", "relpath"])
SymlinkdPath = namedtuple("Path", ["path", "relpath", "real_relpath"])

class GitMtimes(object):
    def __init__(self, root_folder, parent_dir, timestamps_for=None, include=None, exclude=None, silent=False, with_cache=True):
        self.silent = silent
        self.include = include
        self.exclude = exclude
        self.with_cache = with_cache
        self.parent_dir = parent_dir
        self.root_folder = root_folder
        self.timestamps_for = timestamps_for

    def find(self):
        """
        Use git to find the mtimes of the files we care about
        """
        mtimes = {}

        git = Repo(self.root_folder)
        all_files = set([fn.decode('utf-8') for fn in git.open_index()])
        use_files = self.find_files_for_use(all_files)

        # the git index won't find the files under a symlink :(
        # And we include files under a symlink as seperate copies of the files
        # So we still want to generate modified times for those files
        extras = self.extra_symlinked_files(use_files)

        # Combine use_files and extras
        for path in extras:
            use_files.add(path)

        # Tell the user something
        if not self.silent:
            log.info("Finding modified times for %s/%s git controlled files in %s", len(use_files), len(all_files), self.root_folder)

        # Finally get the dates from git!
        return self.commit_dates_for(git, use_files)

    def commit_dates_for(self, git, use_files):
        mtimes = {}
        first_commit = None
        cached_commit = None
        cached_mtimes = {}

        # Use real_relpath if it exists (SymlinkdPath) and default to just relpath
        # This is because we _want_ to compare the commits to the _real paths_
        # As git only cares about the symlink itself, rather than files under it
        # We might have also excluded these unsymlinked files, so we still need them
        # to calcualte the mtimes for these symlinkd files that weren't excluded
        use_files_paths = set([getattr(p, "real_relpath", p.path) for p in use_files])

        if self.with_cache:
            cached_commit, cached_mtimes = self.get_cached_mtimes(use_files)

        for entry in git.get_walker():
            if first_commit is None:
                first_commit = entry.commit.id.decode('utf-8')

            if cached_commit and entry.commit.id.decode('utf-8') == cached_commit:
                mtimes = cached_mtimes
                break

            file_to_mtimes = list(self.mtimes_from_commit(mtimes, entry, use_files_paths))
            if file_to_mtimes:
                for fle, date in file_to_mtimes:
                    mtimes[fle] = date

                if len(use_files_paths - set(mtimes)) == 0:
                    break

        # Finally, we add in our symlnkd files
        for path in use_files:
            if hasattr(path, "real_relpath"):
                mtimes[path.relpath] = mtimes[path.real_relpath]

        if self.with_cache and first_commit != cached_commit:
            self.set_cached_mtimes(first_commit, mtimes, use_files)

        return mtimes

    def mtimes_from_commit(self, mtimes, entry, use_files):
        date = entry.commit.author_time

        for changes in entry.changes():
            if type(changes) is not list:
                changes = [changes]

            for change in changes:
                path = change.new.path.decode('utf-8')
                if self.root_folder and path and self.parent_dir:
                    if path in use_files:
                        new_relpath = os.path.relpath(os.path.join(self.root_folder, path), self.parent_dir)
                        if not new_relpath.startswith("../"):
                            if mtimes.get(new_relpath, 0) < date:
                                yield new_relpath, date

    def extra_symlinked_files(self, potential_symlinks):
        for path in list(potential_symlinks):
            relpath = path.relpath
            location = os.path.join(self.root_folder, relpath)
            real_location = os.path.realpath(location)

            if os.path.islink(location) and os.path.isdir(real_location):
                for root, dirs, files in os.walk(real_location, followlinks=True):
                    for name in files:
                        full_path = os.path.join(root, name)
                        rel_location = os.path.relpath(full_path, real_location)

                        # So this is joining the name of the symlink
                        # With the name of the file, relative to the real location of the symlink
                        # Not complex at all!
                        symlinkd_path = os.path.join(relpath, rel_location)

                        # We then get that relative to the parent dir
                        symlinkd_relpath = os.path.relpath(os.path.realpath(full_path), os.path.realpath(self.parent_dir))

                        # And we need to original file location so we can get a commit time for the symlinkd path
                        real_relpath = os.path.relpath(full_path, os.path.realpath(self.parent_dir))

                        yield SymlinkdPath(symlinkd_path, symlinkd_relpath, real_relpath)

    def find_files_for_use(self, all_files):
        use_files = set()

        for path in all_files:
            relpath = os.path.relpath(os.path.join(self.root_folder, path), self.parent_dir)

            # Only include files under the parent_dir
            if relpath.startswith("../"):
                continue

            # Ignore files that we don't want timestamps from
            if self.timestamps_for is not None and type(self.timestamps_for) is list:
                match = False
                for line in self.timestamps_for:
                    if fnmatch.fnmatch(relpath, line):
                        match = True
                        break
                if not match:
                    continue

            # Matched is true by default if
            # * Have exclude
            # * No exclude and no include
            matched = self.exclude or not any([self.exclude, self.include])

            # Anything not matching exclude gets included
            if self.exclude:
                for line in self.exclude:
                    if fnmatch.fnmatch(relpath, line):
                        matched = False

            # Anything matching include gets included
            if self.include:
                for line in self.include:
                    if fnmatch.fnmatch(relpath, line):
                        matched = True
                        break

            # Either didn't match any exclude or matched an include
            if matched:
                use_files.add(Path(path, relpath))

        return use_files

    def get_cached_mtimes(self, use_files, get_all=False):
        location = os.path.join(self.root_folder, ".git", "harpoon_cached_mtimes.json")
        sorted_use_files_relpaths = sorted([p.relpath for p in use_files])
        result = []
        if os.path.exists(location):
            try:
                result = json.load(open(location))
            except (TypeError, ValueError) as error:
                log.warning("Failed to open harpoon cached mtimes\tlocation=%s\terror=%s", location, error)
            else:
                if type(result) is not list or not all(type(item) is dict for item in result):
                    log.warning("Harpoon cached mtimes needs to be a list of dictionaries\tlocation=%s\tgot=%s", location, type(result))
                    result = []

        if get_all:
            return result

        for item in result:
            if sorted(item.get("use_files_relpaths", [])) == sorted_use_files_relpaths and item.get("parent_dir") == self.parent_dir:
                return item.get("commit"), item.get("mtimes")

        return None, {}

    def set_cached_mtimes(self, first_commit, mtimes, use_files):
        location = os.path.join(self.root_folder, ".git", "harpoon_cached_mtimes.json")
        sorted_use_files_relpaths = sorted([p.relpath for p in use_files])
        current = self.get_cached_mtimes(use_files, get_all=True)

        found = False
        for item in current:
            if sorted(item.get("use_files_relpaths", [])) == sorted_use_files_relpaths:
                item["mtimes"] = mtimes
                item["commit"] = first_commit
                found = True
                break

        if not found:
            current.append({"commit": first_commit, "parent_dir": self.parent_dir, "mtimes": mtimes, "use_files_relpaths": sorted_use_files_relpaths})

        try:
            log.info("Writing harpoon cached mtimes\tlocation=%s", location)
            with open(location, "w") as fle:
                json.dump(current, fle)
        except (TypeError, ValueError, IOError) as error:
            log.warning("Failed to dump harpoon mtime cache\tlocation=%s\terror=%s", location, error)

