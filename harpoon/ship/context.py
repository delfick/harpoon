"""
Docker is a server-client architecture where the client interacts with the server
via http. This means the server doesn't see the directory where the client is
executing from and thus has no access to files around the Dockerfile.

This means that to include anything from the local directory, it must first be
sent to the server in a zip file.

Here we define the class that builds this "context" zip file.
"""

from harpoon.helpers import a_temp_file
from harpoon.errors import HarpoonError

from delfick_app import command_output
from contextlib import contextmanager
from dulwich.repo import Repo
import tempfile
import fnmatch
import logging
import tarfile
import shutil
import json
import six
import os
import re

log = logging.getLogger("harpoon.ship.context")

class ContextWrapper(object):
    """Wraps a tarfile context, so we can continue changing it afterwards"""
    def __init__(self, t, tmpfile):
        self.t = t
        self.tmpfile = tmpfile

    def close(self):
        self.t.close()
        self.tmpfile.flush()
        self.tmpfile.seek(0)

    @property
    def name(self):
        return self.tmpfile.name

    @contextmanager
    def clone_with_new_dockerfile(self, conf, docker_file):
        """Clone this tarfile and add in another filename before closing the new tar and returning"""
        log.info("Copying context to add a different dockerfile")
        self.close()
        with a_temp_file() as tmpfile:
            old_t = os.stat(self.tmpfile.name).st_size > 0
            if old_t:
                shutil.copy(self.tmpfile.name, tmpfile.name)

            with tarfile.open(tmpfile.name, mode="a") as t:
                conf.add_docker_file_to_tarfile(docker_file, t)
                yield ContextWrapper(t, tmpfile)

class ContextBuilder(object):
    """
    Understands how to build a context

    Can take into account git to determine what to include and exclude.
    """
    @contextmanager
    def make_context(self, context, silent_build=False, extra_context=None):
        """
        Context manager for creating the context of the image

        Arguments:

        context - ``harpoon.option_spec.image_objs.Context``
            Knows all the context related options

        docker_file - ``harpoon.option_spec.image_objs.Dockerfile``
            Knows what is in the dockerfile and it's mtime

        silent_build - boolean
            If True, then suppress printing out information

        extra_context - List of (string, string)
            First string represents the content to put in a file and the second
            string represents where in the context this extra file should go
        """
        with a_temp_file() as tmpfile:
            t = tarfile.open(mode='w', fileobj=tmpfile)
            for thing, mtime, arcname in self.find_mtimes(context, silent_build):
                if mtime:
                    os.utime(thing, (mtime, mtime))

                log.debug("Context: {0}".format(arcname))
                t.add(thing, arcname=arcname)

            if extra_context:
                extra = list(extra_context)
                for content, arcname in extra:
                    mtime_match = re.search("mtime\((\d+)\)$", arcname)
                    specified_mtime = None if not mtime_match else int(mtime_match.groups()[0])

                    with self.the_context(content, silent_build=silent_build) as fle:
                        if specified_mtime:
                            os.utime(fle.name, (specified_mtime, specified_mtime))

                        log.debug("Context: {0}".format(arcname))
                        t.add(fle.name, arcname=arcname)

            yield ContextWrapper(t, tmpfile)

    @contextmanager
    def the_context(self, content, silent_build=False):
        """Return either a file with the content written to it, or a whole new context tar"""
        if isinstance(content, six.string_types):
            with a_temp_file() as fle:
                fle.write(content.encode('utf-8'))
                fle.seek(0)
                yield fle
        else:
            with ContextBuilder().make_context(content["context"], silent_build=silent_build) as wrapper:
                wrapper.close()
                yield wrapper.tmpfile

    def find_mtimes(self, context, silent_build):
        """
        Return [(filename, mtime), ...] for all the files.

        Where the mtime comes from git or is None depending on the value of
        use_git_timestamps

        use_git_timestamps can be True indicating all files or it can be a list
        of globs indicating which files should receive git timestamps.
        """
        if not context.enabled:
            return

        mtimes = {}
        if context.use_git:
            mtimes = self.find_git_mtimes(context, silent_build)
        files, mtime_ignoreable = self.find_files(context, silent_build)

        for path in files:
            relname = os.path.relpath(path, context.parent_dir)
            arcname = "./{0}".format(relname.encode('utf-8').decode('ascii', 'ignore'))
            if os.path.exists(path):
                if not context.use_git_timestamps or relname in mtime_ignoreable:
                    yield path, None, arcname
                else:
                    yield path, mtimes.get(relname), arcname

    def find_files(self, context, silent_build):
        """
        Find the set of files from our parent_dir that we care about
        """
        first_layer = ["'{0}'".format(thing) for thing in os.listdir(context.parent_dir)]
        output, status = command_output("find {0} -type l -or -type f -follow -print".format(' '.join(first_layer)), cwd=context.parent_dir)
        if status != 0:
            raise HarpoonError("Couldn't find the files we care about", output=output, cwd=context.parent_dir)
        all_files = set(self.convert_nonascii(output))
        total_files = set(all_files)

        combined = set(all_files)
        mtime_ignoreable = set()

        if context.use_git:
            if context.use_gitignore and context.parent_dir == context.git_root:
                all_files = set([path for path in all_files if not path.startswith(".git")])

            combined = set(all_files)
            changed_files, untracked_files, valid_files = self.find_ignored_git_files(context, silent_build)
            mtime_ignoreable = set(list(changed_files) + list(untracked_files))

            removed = set()
            if valid_files:
                for fle in combined:
                    if fle not in valid_files:
                        removed.add(fle)
            if removed and not silent_build: log.info("Ignoring %s/%s files", len(removed), len(combined))
            combined -= removed

        if context.exclude:
            excluded = set()
            for filename in combined:
                for excluder in context.exclude:
                    if fnmatch.fnmatch(filename, excluder):
                        excluded.add(filename)
                        break
            if not silent_build: log.info("Filtering %s/%s items\texcluding=%s", len(excluded), len(combined), context.exclude)
            combined -= excluded

        if context.include:
            extra_included = []
            for filename in total_files:
                for includer in context.include:
                    if fnmatch.fnmatch(filename, includer):
                        extra_included.append(filename)
                        break
            if not silent_build: log.info("Adding back %s items\tincluding=%s", len(extra_included), context.include)
            combined = set(list(combined) + extra_included)

        files = sorted(os.path.join(context.parent_dir, filename) for filename in combined)
        if not silent_build: log.info("Adding %s things from %s to the context", len(files), context.parent_dir)
        return files, mtime_ignoreable

    def find_git_mtimes(self, context, silent_build):
        """
        Use git to find the mtimes of the files we care about
        """
        if not context.use_git_timestamps:
            return {}

        parent_dir = context.parent_dir
        root_folder = context.git_root

        # Can't use git timestamps if it's just a shallow clone
        # Otherwise all the files get the timestamp of the latest commit
        if context.use_git_timestamps and os.path.exists(os.path.join(root_folder, ".git", "shallow")):
            raise HarpoonError("Can't get git timestamps from a shallow clone", directory=parent_dir)

        git = Repo(root_folder)
        mtimes = {}
        all_files = set(git.open_index())

        use_files = set()
        use_files_relpaths = set()
        for filename in all_files:
            relpath = os.path.relpath(os.path.join(root_folder, filename.decode('utf-8')), context.parent_dir)

            # Only include files under the parent_dir
            if relpath.startswith("../"):
                continue

            # Ignore files that we don't want git_timestamps from
            if context.use_git_timestamps and type(context.use_git_timestamps) is not bool:
                match = False
                for line in context.use_git_timestamps:
                    if fnmatch.fnmatch(relpath, line):
                        match = True
                        break
                if not match:
                    continue

            # Matched is true by default if
            # * Have context.exclude
            # * No context.exclude and no context.include
            matched = context.exclude or not any([context.exclude, context.include])

            # Anything not matching exclude gets included
            if context.exclude:
                for line in context.exclude:
                    if fnmatch.fnmatch(relpath, line):
                        matched = False

            # Anything matching include gets included
            if context.include:
                for line in context.include:
                    if fnmatch.fnmatch(relpath, line):
                        matched = True
                        break

            # Either didn't match any exclude or matched an include
            if matched:
                use_files.add(filename)
                use_files_relpaths.add(relpath)

        if not silent_build: log.info("Finding modified times for %s/%s git controlled files in %s", len(use_files), len(all_files), root_folder)

        first_commit = None
        cached_commit, cached_mtimes = self.get_cached_mtimes(root_folder, use_files_relpaths)
        for entry in git.get_walker():
            if first_commit is None:
                first_commit = entry.commit.id.decode('utf-8')

            if cached_commit and entry.commit.id.decode('utf-8') == cached_commit:
                new_mtimes = cached_mtimes
                new_mtimes.update(mtimes)
                mtimes = new_mtimes
                break

            date = entry.commit.author_time
            added = False
            for changes in entry.changes():
                if type(changes) is not list:
                    changes = [changes]
                for change in changes:
                    path = change.new.path
                    if root_folder and change.new.path and context.parent_dir:
                        if path in use_files:
                            new_relpath = os.path.relpath(os.path.join(root_folder, change.new.path.decode('utf-8')), context.parent_dir).encode('utf-8')
                            if not new_relpath.decode('utf-8').startswith("../"):
                                if mtimes.get(new_relpath, 0) < date:
                                    mtimes[new_relpath] = date
                                    added = True

            if added:
                if len(use_files - set(mtimes)) == 0:
                    break

        mtimes = dict((fn.decode('utf-8') if hasattr(fn, "decode") else fn, mtime) for fn, mtime in mtimes.items())
        if first_commit != cached_commit:
            self.set_cached_mtimes(root_folder, first_commit, mtimes, use_files_relpaths)
        return mtimes

    def get_cached_mtimes(self, root_folder, use_files_relpaths, get_all=False):
        location = os.path.join(root_folder, ".git", "harpoon_cached_mtimes.json")
        sorted_use_files_relpaths = sorted(use_files_relpaths)
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
            if sorted(item.get("use_files_relpaths", [])) == sorted_use_files_relpaths:
                return item.get("commit"), item.get("mtimes")

        return None, {}

    def set_cached_mtimes(self, root_folder, first_commit, mtimes, use_files_relpaths):
        location = os.path.join(root_folder, ".git", "harpoon_cached_mtimes.json")
        sorted_use_files_relpaths = sorted(use_files_relpaths)
        current = self.get_cached_mtimes(root_folder, use_files_relpaths, get_all=True)

        found = False
        for item in current:
            if sorted(item.get("use_files_relpaths", [])) == sorted_use_files_relpaths:
                item["mtimes"] = mtimes
                item["commit"] = first_commit
                found = True
                break

        if not found:
            current.append({"commit": first_commit, "mtimes": mtimes, "use_files_relpaths": sorted_use_files_relpaths})

        try:
            log.info("Writing harpoon cached mtimes\tlocation=%s", location)
            with open(location, "w") as fle:
                json.dump(current, fle)
        except (TypeError, ValueError, IOError) as error:
            log.warning("Failed to dump harpoon mtime cache\tlocation=%s\terror=%s", location, error)

    def convert_nonascii(self, lst):
        """Convert the strange outputs from git commands"""
        for item in lst:
            if item.startswith('"') and item.endswith('"'):
                item = item[1:-1]
                yield item.decode('unicode-escape')
            else:
                yield item.encode('utf-8').decode('unicode-escape')

    def find_ignored_git_files(self, context, silent_build):
        """
        And all the files that are untracked

        And all the files that have been changed

        And find the files that are either under source control or untracked

        return (changed_files, untracked_files, valid_files)
        """
        def git(args, error_message, **error_kwargs):
            output, status = command_output("git {0}".format(args), cwd=context.parent_dir)
            if status != 0:
                error_kwargs['output'] = output
                error_kwargs['directory'] = context.parent_dir
                raise HarpoonError(error_message, **error_kwargs)
            return output

        # Dulwich doesn't include gitignore functionality and so has to be implemented here
        # I don't feel confident in my ability to implement that detail, so we just ask git for that information
        changed_files = git("diff --name-only", "Failed to determine what files have changed")
        untracked_files = git("ls-files --others --exclude-standard", "Failed to find untracked files")

        valid = set()
        if context.use_gitignore:
            under_source_control = git("ls-files --exclude-standard", "Failed to find all the files under source control")
            valid = under_source_control + untracked_files

            for filename in valid:
                location = os.path.join(context.parent_dir, filename)
                if os.path.islink(location) and os.path.isdir(location):
                    actual_path = os.path.abspath(os.path.realpath(location))
                    parent_dir = os.path.abspath(os.path.realpath(context.parent_dir))
                    include_from = os.path.relpath(actual_path, parent_dir)

                    to_include = git("ls-files --exclude-standard -- {0}".format(include_from), "Failed to find files under a symlink")
                    for found in to_include:
                        valid += [os.path.join(filename, os.path.relpath(found, include_from))]

        to_set = lambda lst: set(self.convert_nonascii(lst))
        return to_set(changed_files), to_set(untracked_files), to_set(valid)

