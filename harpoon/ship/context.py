"""
Docker is a server-client architecture where the client interacts with the server
via http. This means the server doesn't see the directory where the client is
executing from and thus has no access to files around the Dockerfile.

This means that to include anything from the local directory, it must first be
sent to the server in a zip file.

Here we define the class that builds this "context" zip file.
"""

from harpoon.errors import HarpoonError, BadOption
from harpoon.helpers import a_temp_file

from contextlib import contextmanager
from six import BytesIO
import subprocess
import tempfile
import tarfile
import fnmatch
import logging
import shutil
import docker
import shlex
import six
import os
import re

regexes = {"whitespace": re.compile(r"\s+")}

log = logging.getLogger("harpoon.ship.context")


def command_output(command, cwd=None):
    try:
        output = subprocess.check_output(shlex.split(command), cwd=cwd)
        code = 0
    except subprocess.CalledProcessError as error:
        output = error.output
        code = error.returncode

    lines = [line for line in output.decode().split("\n") if line.strip()]
    return lines, code


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

        silent_build - boolean
            If True, then suppress printing out information

        extra_context - List of (content, string)
            content is either a string repsenting the content to put in a file
            or a dictionary representing what path to get from what docker image

            The second string represents where in the context this extra file should go
        """
        with a_temp_file() as tmpfile:
            t = tarfile.open(mode="w", fileobj=tmpfile)
            for thing, arcname in self.find_files_for_tar(context, silent_build):
                log.debug("Context: {0}".format(arcname))
                t.add(thing, arcname=arcname)

            if extra_context:
                extra = list(extra_context)
                for content, arcname in extra:
                    if arcname == "":
                        continue

                    with self.the_context(content, silent_build=silent_build) as fle:
                        log.debug("Context: {0}".format(arcname))
                        t.add(fle.name, arcname=arcname)

            yield ContextWrapper(t, tmpfile)

    @contextmanager
    def the_context(self, content, silent_build=False):
        """Return either a file with the content written to it, or a whole new context tar"""
        if isinstance(content, six.string_types):
            with a_temp_file() as fle:
                fle.write(content.encode("utf-8"))
                fle.seek(0)
                yield fle
        elif "context" in content:
            with ContextBuilder().make_context(
                content["context"], silent_build=silent_build
            ) as wrapper:
                wrapper.close()
                yield wrapper.tmpfile
        elif "image" in content:
            from harpoon.ship.runner import Runner

            with a_temp_file() as fle:
                content["conf"].command = "yes"
                with Runner()._run_container(
                    content["conf"], content["images"], detach=True, delete_anyway=True
                ):
                    try:
                        strm, stat = content["docker_api"].get_archive(
                            content["conf"].container_id, content["path"]
                        )
                    except docker.errors.NotFound:
                        raise BadOption(
                            "Trying to get something from an image that don't exist!",
                            path=content["path"],
                            image=content["conf"].image_name,
                        )
                    else:
                        log.debug(stat)

                        fo = BytesIO(b"".join(strm))

                        # In newer docker the archive is a gzipped archive
                        # But in older docker, it's a normal tar
                        for mode in ("r:gz", "r"):
                            try:
                                tf = tarfile.open(fileobj=fo, mode=mode)
                                break
                            except tarfile.ReadError:
                                if mode == "r":
                                    raise
                                fo.seek(0)

                        if tf.firstmember.isdir():
                            tf2 = tarfile.TarFile(fileobj=fle, mode="w")
                            name = tf.firstmember.name
                            for member in tf.getmembers()[1:]:
                                member.name = member.name[len(name) + 1 :]
                                if member.issym():
                                    with tempfile.NamedTemporaryFile() as symfle:
                                        os.remove(symfle.name)
                                        os.symlink(member.linkpath, symfle.name)
                                        tf2.addfile(member, fileobj=symfle)
                                elif not member.isdir():
                                    tf2.addfile(member, fileobj=tf.extractfile(member.name))
                            tf2.close()
                        else:
                            fle.write(tf.extractfile(tf.firstmember.name).read())

                        tf.close()
                        log.info(
                            "Got '{0}' from {1} for context".format(
                                content["path"], content["conf"].container_id
                            )
                        )

                fle.seek(0)
                yield fle

    def find_files_for_tar(self, context, silent_build):
        """
        Return [(filename, arcname), ...] for all the files.
        """
        if not context.enabled:
            return

        files = self.find_files(context, silent_build)

        for path in files:
            relname = os.path.relpath(path, context.parent_dir)
            arcname = "./{0}".format(relname.encode("utf-8").decode("ascii", "ignore"))
            if os.path.exists(path):
                yield path, arcname

    def find_files(self, context, silent_build):
        """
        Find the set of files from our parent_dir that we care about
        """
        first_layer = ["'{0}'".format(thing) for thing in os.listdir(context.parent_dir)]
        output, status = command_output(
            "find {0} -type l -or -type f {1} -follow -print".format(
                " ".join(first_layer), context.find_options
            ),
            cwd=context.parent_dir,
        )
        if status != 0:
            if context.ignore_find_errors:
                log.warning("The find command failed to run, will continue anyway")
            else:
                raise HarpoonError(
                    "Couldn't find the files we care about", output=output, cwd=context.parent_dir
                )
        all_files = set(self.convert_nonascii(output))
        total_files = set(all_files)

        combined = set(all_files)

        if context.use_gitignore:
            if context.parent_dir == context.git_root:
                all_files = set([path for path in all_files if not path.startswith(".git")])

            combined = set(all_files)
            valid_files = self.find_notignored_git_files(context, silent_build)

            removed = set()
            if valid_files:
                for fle in combined:
                    if fle not in valid_files:
                        removed.add(fle)
            if removed and not silent_build:
                log.info("Ignoring %s/%s files", len(removed), len(combined))
            combined -= removed

        if context.exclude:
            excluded = set()
            for filename in combined:
                for excluder in context.exclude:
                    if fnmatch.fnmatch(filename, excluder):
                        excluded.add(filename)
                        break
            if not silent_build:
                log.info(
                    "Filtering %s/%s items\texcluding=%s",
                    len(excluded),
                    len(combined),
                    context.exclude,
                )
            combined -= excluded

        if context.include:
            extra_included = []
            for filename in total_files:
                for includer in context.include:
                    if fnmatch.fnmatch(filename, includer):
                        extra_included.append(filename)
                        break
            if not silent_build:
                log.info("Adding back %s items\tincluding=%s", len(extra_included), context.include)
            combined = set(list(combined) + extra_included)

        files = sorted(os.path.join(context.parent_dir, filename) for filename in combined)
        if not silent_build:
            log.info("Adding %s things from %s to the context", len(files), context.parent_dir)
        return files

    def convert_nonascii(self, lst):
        """Convert the strange outputs from git commands"""
        for item in lst:
            if item.startswith('"') and item.endswith('"'):
                item = item[1:-1]
                yield item.encode("utf-8").decode("unicode-escape")
            else:
                yield item.encode("utf-8").decode("unicode-escape")

    def find_notignored_git_files(self, context, silent_build):
        """
        Return a list of files that are not ignored by git
        """

        def git(args, error_message, cwd=context.parent_dir, **error_kwargs):
            output, status = command_output("git {0}".format(args), cwd=cwd)
            if status != 0:
                error_kwargs["output"] = output
                error_kwargs["directory"] = context.parent_dir
                raise HarpoonError(error_message, **error_kwargs)
            return output

        untracked_files = git(
            "ls-files --others --exclude-standard", "Failed to find untracked files"
        )

        valid = set()
        under_source_control = git(
            "ls-files --exclude-standard", "Failed to find all the files under source control"
        )
        git_submodules = [
            regexes["whitespace"].split(line.strip())[1]
            for line in git("submodule status", "Failed to find submodules", cwd=context.git_root)
        ]
        git_submodules = [
            os.path.normpath(
                os.path.relpath(
                    os.path.abspath(p),
                    os.path.abspath(os.path.relpath(context.parent_dir, context.git_root)),
                )
            )
            for p in git_submodules
        ]

        valid = under_source_control + untracked_files

        for filename in list(valid):
            matched = False
            if context.exclude:
                for excluder in context.exclude:
                    if fnmatch.fnmatch(filename, excluder):
                        matched = True
                        break

            if matched:
                continue

            location = os.path.join(context.parent_dir, filename)
            if os.path.islink(location) and os.path.isdir(location):
                actual_path = os.path.abspath(os.path.realpath(location))
                parent_dir = os.path.abspath(os.path.realpath(context.parent_dir))
                include_from = os.path.relpath(actual_path, parent_dir)

                to_include = git(
                    "ls-files --exclude-standard -- {0}".format(include_from),
                    "Failed to find files under a symlink",
                )
                for found in to_include:
                    valid += [os.path.join(filename, os.path.relpath(found, include_from))]
            elif os.path.isdir(location) and filename in git_submodules:
                to_include = git(
                    "ls-files --exclude-standard",
                    "Failed to find files in a submodule",
                    cwd=location,
                )
                valid = [v for v in valid if v != filename]
                for found in to_include:
                    valid.append(os.path.join(filename, found))

        return set(self.convert_nonascii(valid))
