from harpoon.errors import DeprecatedFeature, HarpoonError
from harpoon.formatter import MergedOptionStringFormatter

from input_algorithms.spec_base import NotSpecified
from harpoon.errors import BadCommand, BadOption
from input_algorithms.dictobj import dictobj
from harpoon.processes import command_output
from harpoon.helpers import a_temp_file
from contextlib import contextmanager
import logging
import fnmatch
import tarfile
import hashlib
import glob2
import uuid
import os

log = logging.getLogger("option_spec.image_objs")

class Image(dictobj):
    fields = [
          "commands", "links", "context"
        , "lxc_conf", "volumes", "env", "ports"
        , "other_options", "network", "privileged", "name_prefix"
        , "image_name", "image_index", "dependency_options"
        , "container_name", "name", "key_name"
        ]

    @property
    def image_name(self):
        if getattr(self, "_image_name", NotSpecified) is NotSpecified:
            if self.name_prefix:
                self._image_name = "{0}-{1}".format(self.name_prefix, self.name)
            else:
                self._image_name = self.name

            if self.image_index:
                self._image_name = "{0}{1}".format(self.image_index, self._image_name)
        return self._image_name

    @image_name.setter
    def image_name(self, val):
        self._image_name = val

    @property
    def container_name(self):
        if getattr(self, "_container_name", NotSpecified) is NotSpecified:
            self.container_name = "{0}-{1}".format(self.image_name.replace("/", "--"), str(uuid.uuid1()).lower())
        return self._container_name

    @property
    def formatted_command(self):
        if self.bash:
            return "/bin/bash -c '{0}'".format(self.bash)
        else:
            return self.command

    @container_name.setter
    def container_name(self, val):
        self._container_name = val

    def dependencies(self, images):
        """Yield just the dependency images"""
        for image, _ in self.dependency_images(images):
            yield image

    def dependency_images(self, images, ignore_parent=False):
        """
        What images does this one require

        Taking into account parent image, and those in link and volumes.share_with options
        """
        candidates = []
        detach = dict((candidate, not options.attached) for candidate, options in self.dependency_options.items())

        if not ignore_parent:
            if not isinstance(self.commands.parent_image, basestring):
                candidates.append(self.commands.parent_image.name)

        for link in self.links:
            if link.container:
                candidates.append(link.container)

        for container in self.volumes.share_with:
            if not isinstance(container, basestring):
                candidates.append(container)

        done = set()
        for candidate in candidates:
            if candidate not in done:
                done.add(candidate)
                yield candidate, detach.get(candidate, True)

    def find_missing_env(self):
        """Find any missing environment variables"""
        missing = []
        for e in self.env:
            if not e.default_val and not e.set_val:
                if e.env_name not in os.environ:
                    missing.append(e.env_name)

        if missing:
            raise BadOption("Some environment variables aren't in the current environment", missing=missing)

    def display_line(self):
        """A single line describing this image"""
        msg = ["Image {0}".format(self.name)]
        if self.image_index:
            msg.append("Pushes to {0}".format(self.image_name))
        return ' : '.join(msg)

class Command(dictobj):
    fields = ['meta', 'orig_command']

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        self.extra_context = []

    @property
    def commands(self):
        if not getattr(self, "_commands", None):
            self._commands = []
            for command in self.orig_command:
                for cmd in self.determine_commands(self.meta, command):
                    self._commands.append(cmd)
        return self._commands

    @property
    def parent_image(self):
        if hasattr(self, "_commands"):
            for name, command in self._commands:
                if name == "FROM":
                    return command

        for command in self.orig_command:
            cmd = command
            if isinstance(command, dict):
                cmd = command.items()[0]

            if isinstance(command, list):
                cmd, _ = command

            if cmd.startswith("FROM"):
                val = list(self.determine_commands(self.meta, command))[0][1]
                return val

    @property
    def parent_image_name(self):
        """Return the image name of the parent"""
        parent = self.parent_image
        if isinstance(parent, basestring):
            return parent
        else:
            return parent.image_name

    def docker_file(self):
        res = []
        for name, value in self.commands:
            if name == "FROM" and not isinstance(value, basestring):
                value = value.image_name
            res.append("{0} {1}".format(name, value))

        return '\n'.join(res)


    def determine_commands(self, meta, command):
        errors = []
        if not command:
            return

        elif isinstance(command, (str, unicode)):
            yield command.split(" ", 1)
            return

        if isinstance(command, dict):
            command = command.items()
            if len(command) > 1:
                errors.append(BadCommand("Command spec as a dictionary can only be one {key: val}", found_length=len(command)))

            command = command[0]

        if len(command) != 2:
            errors.append(BadCommand("Command spec as a list can only be two items", found_length=len(command), found=command))

        name, value = command
        if not isinstance(name, basestring):
            errors.append(BadCommand("Command spec must have a string value as the first option", found=command))
        elif isinstance(value, basestring):
            if name == "FROM" and value.endswith(".image_name}"):
                raise DeprecatedFeature("Just specify the image in the FROM, not it's image_name", value=value, meta=meta)

            value = [MergedOptionStringFormatter(meta.everything, "commands", value=value).format()]
            if name == "FROM":
                if not isinstance(value, basestring):
                    yield name, value[0]
                    return

        if isinstance(value, dict):
            try:
                for part in self.complex_spec(name, value):
                    yield part
            except BadCommand as error:
                errors.append(error)
        else:
            for part in value:
                yield name, part

            if not value:
                errors.append(BadCommand("Command spec must be a string or a list", found=command))

        if errors:
            raise BadCommand("Command spec had errors", path=meta.path, source=meta.source, _errors=errors)

    def complex_spec(self, name, value):
        """Turn a complex command spec into a list of "KEY VALUE" strings"""
        if name == "ADD":
            if "content" in value:
                if "dest" not in value:
                    raise BadOption("When doing an ADD with content, must specify dest", image=self.name, command=[name, value])
                dest = value.get("dest")
                context_name = "{0}-{1}".format(hashlib.md5(value.get('content')).hexdigest(), dest.replace("/", "-").replace(" ", "--"))
                self.extra_context.append((value.get("content"), context_name))
                yield "ADD", "{0} {1}".format(context_name, dest)
            else:
                prefix = value.get("prefix", "/")
                if "get" not in value:
                    raise BadOption("Command spec didn't contain 'get' option", command=[name, value], image=self.name)

                get = value["get"]
                if isinstance(get, basestring):
                    get = [get]
                elif not isinstance(get, list):
                    raise BadOption("Command spec value for 'get' should be string or a list", command=[name, value], image=self.name)

                for val in get:
                    yield "ADD", "{0} {1}/{2}".format(val, prefix, val)
        else:
            raise BadOption("Don't understand dictionary value for spec", command=[name, value], image=self.name)

class Link(dictobj):
    fields = ["container_name", "link_name"]

    def pair(self):
        return (self.container_name, self.link_name)

class Context(dictobj):
    fields = ["include", "exclude", "enabled", "parent_dir", "use_gitignore", "use_git_timestamps"]

    @contextmanager
    def make_context(self, parent_dir, docker_lines, mtime, silent_build=False, extra_context=None):
        """Context manager for creating the context of the image"""
        use_git = False
        if self.use_gitignore is not NotSpecified and self.use_gitignore:
            use_git = True
        if self.use_git_timestamps is not NotSpecified and self.use_git_timestamps:
            use_git = True

        files = []
        git_files = set()
        changed_files = set()
        use_git_timestamps = use_git if self.use_git_timestamps is NotSpecified else self.use_git_timestamps

        if self.enabled:
            if use_git:
                output, status = command_output("git rev-parse --show-toplevel", cwd=parent_dir)
                if status != 0:
                    raise HarpoonError("Failed to find top level directory of git repository", directory=parent_dir, output=output)
                top_level = ''.join(output).strip()
                if use_git_timestamps and os.path.exists(os.path.join(top_level, ".git", "shallow")):
                    raise HarpoonError("Can't get git timestamps from a shallow clone", directory=parent_dir)

                output, status = command_output("git diff --name-only", cwd=parent_dir)
                if status != 0:
                    raise HarpoonError("Failed to determine what files have changed", directory=parent_dir, output=output)
                changed_files = set(output)

                if not silent_build: log.info("Determining context from git ls-files")
                options = ""
                if self.exclude:
                    for excluder in self.exclude:
                        options = "{0} --exclude={1}".format(options, excluder)

                # Unfortunately --exclude doesn't work on committed/staged files, only on untracked things :(
                output, status = command_output("git ls-files --exclude-standard", cwd=parent_dir)
                if status != 0:
                    raise HarpoonError("Failed to do a git ls-files", directory=parent_dir, output=output)

                others, status = command_output("git ls-files --exclude-standard --others {0}".format(options), cwd=parent_dir)
                if status != 0:
                    raise HarpoonError("Failed to do a git ls-files to get untracked files", directory=parent_dir, output=others)

                if not (output or others) or any(out and out[0].startswith("fatal: Not a git repository") for out in (output, others)):
                    raise HarpoonError("Told to use git features, but git ls-files says no", directory=parent_dir, output=output, others=others)

                combined = set(output + others)
                git_files = set(output)
            else:
                combined = set()
                if self.exclude:
                    combined = set([os.path.relpath(location, parent_dir) for location in glob2.glob("{0}/**".format(parent_dir))])
                else:
                    combined = set([parent_dir])

            if self.exclude:
                if not silent_build: log.info("Filtering %s items\texcluding=%s", len(combined), self.exclude)
                excluded = set()
                for filename in combined:
                    for excluder in self.exclude:
                        if fnmatch.fnmatch(filename, excluder):
                            excluded.add(filename)
                            break
                combined = combined - excluded

            files = sorted(os.path.join(parent_dir, filename) for filename in combined)
            if self.exclude and not silent_build: log.info("Adding %s things from %s to the context", len(files), parent_dir)

        def matches_glob(string, globs):
            """Returns whether this string matches any of the globs"""
            if isinstance(globs, bool):
                return globs
            return any(fnmatch.fnmatch(string, glob) for glob in globs)

        with a_temp_file() as tmpfile:
            t = tarfile.open(mode='w:gz', fileobj=tmpfile)
            for thing in files:
                if os.path.exists(thing):
                    relname = os.path.relpath(thing, parent_dir)
                    arcname = "./{0}".format(relname)
                    if use_git_timestamps and (relname in git_files and relname not in changed_files and matches_glob(relname, use_git_timestamps)):
                        # Set the modified date from git
                        date, status = command_output("git show -s --format=%at -n1 --", relname, cwd=parent_dir)
                        if status != 0 or not date or not date[0].isdigit():
                            log.error("Couldn't determine git date for a file\tdirectory=%s\trelname=%s", parent_dir, relname)

                        if date:
                            date = int(date[0])
                            os.utime(thing, (date, date))
                    t.add(thing, arcname=arcname)

            if extra_context:
                for content, arcname in extra_context:
                    with a_temp_file() as fle:
                        fle.write(content)
                        fle.seek(0)
                        if mtime:
                            os.utime(fle.name, (mtime, mtime))
                        t.add(fle.name, arcname=arcname)

            # And add our docker file
            with a_temp_file() as dockerfile:
                dockerfile.write(docker_lines)
                dockerfile.seek(0)
                if mtime:
                    os.utime(dockerfile.name, (mtime, mtime))
                t.add(dockerfile.name, arcname="./Dockerfile")

            t.close()
            tmpfile.seek(0)
            yield tmpfile

class Volumes(dictobj):
    fields = ["mount", "share_with"]

    @property
    def share_with_names(self):
        for container in self.share_with:
            if isinstance(container, basestring):
                yield container
            else:
                yield container.container_name

    def mount_options(self):
        return [mount.options() for mount in self.mount]

class Mount(dictobj):
    fields = ["local_path", "container_path", "permissions"]

    def options(self):
        return (self.local_path, self.container_path, self.permissions)

class Environment(dictobj):
    fields = ["env_name", ("default_val", None), ("set_val", None)]

    def pair(self):
        """Get the name and value for this environment variable"""
        if self.set_val:
            return self.env_name, self.set_val
        elif self.default_val:
            return self.env_name, os.environ.get(self.env_name, self.default_val)
        else:
            return self.env_name, os.environ[self.env_name]

class Port(dictobj):
    fields = ["ip", "host_port", "container_port"]

class Network(dictobj):
    fields = ["dns", "mode", "hostname", "disabled", "dns_search", "publish_all_ports"]

class DependencyOptions(dictobj):
    fields = [("attached", False)]

