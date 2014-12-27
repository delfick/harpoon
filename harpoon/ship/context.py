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
import glob2
import os

log = logging.getLogger("harpoon.ship.context")

class ContextBuilder(object):
    """
    Understands how to build a context

    Can take into account git to determine what to include and exclude.
    """
    @contextmanager
    def make_context(self, context, docker_file, silent_build=False, extra_context=None):
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
            t = tarfile.open(mode='w:gz', fileobj=tmpfile)
            for thing, mtime, arcname in self.find_mtimes(context, silent_build):
                if mtime:
                    os.utime(thing, (mtime, mtime))
                t.add(thing, arcname=arcname)

            mtime = docker_file.mtime
            if extra_context:
                for content, arcname in extra_context:
                    with a_temp_file() as fle:
                        fle.write(content.encode('utf-8'))
                        fle.seek(0)
                        if mtime:
                            os.utime(fle.name, (mtime, mtime))
                        t.add(fle.name, arcname=arcname)

            # And add our docker file
            with a_temp_file() as dockerfile:
                dockerfile.write(docker_file.docker_lines.encode('utf-8'))
                dockerfile.seek(0)
                if mtime:
                    os.utime(dockerfile.name, (mtime, mtime))
                t.add(dockerfile.name, arcname="./Dockerfile")

            t.close()
            tmpfile.seek(0)
            yield tmpfile

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
                arcname = "./{0}".format(relname)
                if os.path.exists(path):
                    if not context.use_git_timestamps or relname in mtime_ignoreable:
                        yield path, None, arcname
                    else:
                        yield path, mtimes.get(relname), arcname

    def find_files(self, context, silent_build):
        """
        Find the set of files from our parent_dir that we care about
        """
        all_files = set(os.path.relpath(location, context.parent_dir) for location in glob2.glob("{0}/**".format(context.parent_dir)) if not os.path.isdir(location))
        for path in [os.path.relpath(location, context.parent_dir) for location in glob2.glob("{0}/.*/**".format(context.parent_dir))]:
            all_files.add(path)
        combined = set(all_files)
        mtime_ignoreable = set()

        if context.use_git:
            if context.use_gitignore and context.parent_dir == context.git_root:
                all_files = set([path for path in all_files if not path.startswith(".git")])

            combined = set(all_files)
            mtime_ignoreable, ignored_files = self.find_ignored_git_files(context, silent_build)
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
            for filename in all_files:
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
        context_prefix = os.path.relpath(context.parent_dir, root_folder)
        for filename in all_files:
            # Only include files under the parent_dir
            if os.path.relpath(filename, context_prefix).startswith("../"):
                continue

            # Ignore files that we don't want git_timestamps from
            if context.use_git_timestamps and type(context.use_git_timestamps) is not bool:
                match = False
                for line in context.use_git_timestamps:
                    if fnmatch.fnmatch(filename, line):
                        match = True
                        break
                if not match:
                    continue

            # Matched is true by default if
            # * Have context.exclude
            # * No context.exclude and no context.include
            matched = context.exclude or not any([context.exclude, context.include])

            # Anything not matching exclude gets included
            for line in context.exclude:
                if fnmatch.fnmatch(filename, line):
                    matched = False

            # Anything matching include gets included
            for line in context.include:
                if fnmatch.fnmatch(filename, line):
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
                    if path in use_files and path not in mtimes:
                        mtimes[path] = date

            if len(use_files - set(mtimes)) == 0:
                break

        return mtimes

    def find_ignored_git_files(self, context, silent_build):
        """
        Find all the files that are ignored by git

        Also find all the files that we should ignore mtimes from

        return (mtime_ignoreable, ignored)
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
        mtime_ignoreable = set(changed_files + list(git("ls-files --exclude-standard", "Failed to find untracked files")))

        if context.use_gitignore:
            others = set(git("ls-files --others", "Failed to find ignored files")) - mtime_ignoreable
        else:
            others = set()

        return mtime_ignoreable, others

