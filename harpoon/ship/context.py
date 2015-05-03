"""
Docker is a server-client architecture where the client interacts with the server
via http. This means the server doesn't see the directory where the client is
executing from and thus has no access to files around the Dockerfile.

This means that to include anything from the local directory, it must first be
sent to the server in a zip file.

Here we define the class that builds this "context" zip file.
"""

from harpoon.processes import command_output
from harpoon.helpers import a_temp_file
from harpoon.errors import HarpoonError

from contextlib import contextmanager
from dulwich.repo import Repo
import fnmatch
import logging
import tarfile
import os

log = logging.getLogger("harpoon.ship.context")

class ContextWrapper(object):
    """Wraps a tarfile context, so we can continue changing it afterwards"""
    def __init__(self, t, tmpfile):
        self.t = t
        self.tmpfile = tmpfile

    def close(self):
        self.t.close()
        self.tmpfile.seek(0)

    @property
    def name(self):
        return self.tmpfile.name

    @contextmanager
    def clone_with_new_dockerfile(self, conf, docker_file):
        """Clone this tarfile and add in another filename before closing the new tar and returning"""
        with open(self.tmpfile.name) as old_tmpfile:
            old_t = None
            if os.stat(old_tmpfile.name).st_size > 0:
                old_t = tarfile.open(mode='r:gz', fileobj=open(old_tmpfile.name))

            with a_temp_file() as tmpfile:
                t = tarfile.open(mode='w:gz', fileobj=tmpfile)
                if old_t:
                    for member in old_t:
                        t.addfile(member, old_t.extractfile(member.name))

                conf.add_docker_file_to_tarfile(docker_file, t)
                yield ContextWrapper(t, tmpfile)

class ContextBuilder(object):
    """
    Understands how to build a context

    Can take into account git to determine what to include and exclude.
    """
    @contextmanager
    def make_context(self, context, silent_build=False, extra_context=None, mtime=None):
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
        provided_mtime = mtime
        with a_temp_file() as tmpfile:
            t = tarfile.open(mode='w:gz', fileobj=tmpfile)
            for thing, mtime, arcname in self.find_mtimes(context, silent_build):
                if mtime:
                    os.utime(thing, (mtime, mtime))
                t.add(thing, arcname=arcname)

            if extra_context:
                for content, arcname in extra_context:
                    with a_temp_file() as fle:
                        fle.write(content.encode('utf-8'))
                        fle.seek(0)
                        if mtime:
                            os.utime(fle.name, (provided_mtime, provided_mtime))
                        t.add(fle.name, arcname=arcname)

            yield ContextWrapper(t, tmpfile)

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

        mtimes = self.find_git_mtimes(context, silent_build)
        files, mtime_ignoreable = self.find_files(context, silent_build)

        for path in files:
            if os.path.exists(path):
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
        output, status = command_output("find {0} -type f -print".format(' '.join(first_layer)), cwd=context.parent_dir)
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
            changed_files, untracked_files, ignored_files = self.find_ignored_git_files(context, silent_build)
            mtime_ignoreable = set(list(changed_files) + list(untracked_files) + list(ignored_files))

            removed = set()
            for fle in ignored_files:
                if fle in combined:
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
        for filename in all_files:
            relpath = os.path.relpath(os.path.join(root_folder, filename), context.parent_dir)

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

        if not silent_build: log.info("Finding modified times for %s/%s git controlled files in %s", len(use_files), len(all_files), root_folder)
        for entry in git.get_walker(paths=use_files):
            date = entry.commit.author_time
            for changes in entry.changes():
                if type(changes) is not list:
                    changes = [changes]
                for change in changes:
                    path = change.new.path
                    if root_folder and change.new.path and context.parent_dir:
                        new_relpath = os.path.relpath(os.path.join(root_folder, change.new.path), context.parent_dir)
                        if path in use_files and mtimes.get(new_relpath, 0) < date and not new_relpath.startswith("../"):
                            mtimes[new_relpath] = date

            if len(use_files - set(mtimes)) == 0:
                break

        return mtimes

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
        Find all the files that are ignored by git

        And all the files that are untracked

        And all the files that have been changed

        return (changed_files, untracked_files, ignored_files)
        """
        root_folder = context.git_root
        def git(args, error_message, **error_kwargs):
            output, status = command_output("git {0}".format(args), cwd=root_folder)
            if status != 0:
                error_kwargs['output'] = output
                error_kwargs['directory'] = context.parent_dir
                raise HarpoonError(error_message, **error_kwargs)
            return output

        # Dulwich doesn't include gitignore functionality and so has to be implemented here
        # I don't feel confident in my ability to implement that detail, so we just ask git for that information
        changed_files = git("diff --name-only", "Failed to determine what files have changed")
        untracked_files = git("ls-files --others --exclude-standard", "Failed to find untracked files")

        ignored_files = set()
        if context.use_gitignore:
            ignored_files = git("ls-files --others", "Failed to find ignored files")

        to_set = lambda lst: set(self.convert_nonascii(lst))
        return to_set(changed_files), to_set(untracked_files), to_set(ignored_files) - to_set(untracked_files)

