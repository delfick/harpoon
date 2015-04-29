"""
The Builder is responsible for finding and building docker images in
the correct order

Building an image requires building all dependent images, creating the necessary
context, and actually building the current image.
"""

from harpoon.errors import NoSuchImage, BadCommand, FailedImage, UserQuit
from harpoon.ship.progress_stream import ProgressStream, Failure, Unknown
from harpoon.ship.runner import Runner
from harpoon.layers import Layers

from input_algorithms.spec_base import NotSpecified
from contextlib import contextmanager
from itertools import chain
import humanize
import logging
import uuid
import six
import sys
import os

log = logging.getLogger("harpoon.ship.builder")

########################
###   PROGRESS STREAM
########################

class BuildProgressStream(ProgressStream):
    def setup(self):
        self.current_container = None

    def interpret_line(self, line_detail):
        if "stream" in line_detail:
            self.interpret_stream(line_detail["stream"])
        elif "status" in line_detail:
            self.interpret_status(line_detail["status"])
        else:
            self.interpret_unknown(line_detail)

    def interpret_stream(self, line):
        if line.strip().startswith("---> Running in"):
            self.current_container = line[len("---> Running in "):].strip()
        elif line.strip().startswith("Successfully built"):
            self.current_container = line[len("Successfully built"):].strip()

        if line.strip().startswith("---> Running in"):
            self.cached = False
        elif line.strip().startswith("---> Using cache"):
            self.cached = True

        self.add_line(line)

    def interpret_status(self, line):
        if line.startswith("Pulling image"):
            if not line.endswith("\n"):
                line = "{0}\n".format(line)
        else:
            line = "\r{0}".format(line)

        if "already being pulled by another client" in line or "Pulling repository" in line:
            self.cached = False
        self.add_line(line)

########################
###   BUILDER
########################

class Builder(object):
    """Build an image from Image configuration"""

    ########################
    ###   USAGE
    ########################

    def make_image(self, conf, images, chain=None, parent_chain=None, made=None, ignore_deps=False, ignore_parent=False):
        """Make us an image"""
        made = made or {}
        chain = chain or []
        parent_chain = parent_chain or []

        if conf.name in made:
            return

        if conf.name in chain and not ignore_deps:
            raise BadCommand("Recursive dependency images", chain=chain + [conf.name])

        if conf.name in parent_chain and not ignore_parent:
            raise BadCommand("Recursive FROM statements", chain=parent_chain + [conf.name])

        if conf.name not in images:
            raise NoSuchImage(looking_for=conf.name, available=images.keys())

        if not ignore_deps:
            for dependency, image in conf.dependency_images():
                self.make_image(images[dependency], images, chain=chain + [conf.name], made=made, ignore_deps=True)

        if not ignore_parent:
            parent_image = conf.commands.parent_image
            if not isinstance(parent_image, six.string_types):
                self.make_image(parent_image, images, chain, parent_chain + [conf.name], made=made, ignore_deps=True)

        # Should have all our dependencies now
        log.info("Making image for '%s' (%s) - FROM %s", conf.name, conf.image_name, conf.commands.parent_image_name)
        self.build_image(conf)
        made[conf.name] = True

    def build_image(self, conf):
        """Build this image"""
        with self.context(conf) as context:
            try:
                stream = BuildProgressStream(conf.harpoon.silent_build)
                with self.remove_replaced_images(conf):
                    if conf.recursive is NotSpecified:
                        self.do_build(conf, context, stream)
                    else:
                        self.do_recursive_build(conf, context, stream)
            except (KeyboardInterrupt, Exception) as error:
                exc_info = sys.exc_info()
                if stream.current_container:
                    Runner().stage_build_intervention(conf, stream.current_container)

                if isinstance(error, KeyboardInterrupt):
                    raise UserQuit()
                else:
                    six.reraise(*exc_info)

    def layered(self, images, only_pushable=False):
        """Yield layers of images"""
        if only_pushable:
            operate_on = dict((image, instance) for image, instance in images.items() if instance.image_index)
        else:
            operate_on = images

        layers = Layers(operate_on, all_images=images)
        layers.add_all_to_layers()
        return layers.layered

    ########################
    ###   UTILITY
    ########################

    @contextmanager
    def context(self, conf):
        with conf.make_context() as context:
            self.log_context_size(context, conf)
            yield context

    def log_context_size(self, context, conf):
        context_size = humanize.naturalsize(os.stat(context.name).st_size)
        log.info("Building '%s' in '%s' with %s of context", conf.name, conf.context.parent_dir, context_size)

    @contextmanager
    def remove_replaced_images(self, conf):
        current_ids = None
        if not conf.harpoon.keep_replaced:
            images = conf.harpoon.docker_context.images()
            current_ids = [image["Id"] for image in images if "{0}:latest".format(conf.image_name) in image["RepoTags"]]

        yield

        if current_ids:
            images = conf.harpoon.docker_context.images()
            untagged = [image["Id"] for image in images if image["RepoTags"] == ["<none>:<none>"]]
            for image in current_ids:
                if image in untagged:
                    log.info("Deleting replaced image\ttag=%s\told_hash=%s", "{0}:latest".format(conf.image_name), image)
                    try:
                        conf.harpoon.docker_context.remove_image(image)
                    except Exception as error:
                        log.error("Failed to remove replaced image\thash=%s\terror=%s", image, error)

    def do_build(self, conf, context, stream, image_name=None, verbose=False):
        if image_name is None:
            image_name = conf.image_name

        context.close()
        for line in conf.harpoon.docker_context.build(fileobj=context.tmpfile, custom_context=True, tag=image_name, stream=True, rm=True):
            try:
                stream.feed(line)
            except Failure as error:
                raise FailedImage("Failed to build an image", image=conf.name, msg=error)
            except Unknown as error:
                log.warning("Unknown line\tline=%s", error)

            for part in stream.printable():
                sys.stdout.write(part.encode("utf-8", "replace"))
            sys.stdout.flush()

        return stream.cached

    def do_recursive_build(self, conf, context, stream):
        """Do a recursive build!"""
        from harpoon.option_spec.image_objs import Volumes
        from harpoon.ship.runner import Runner
        conf_image_name = conf.name
        if conf.image_name_prefix is not NotSpecified:
            conf_image_name = "{0}-{1}".format(conf.image_name_prefix, conf.name)

        with self.remove_replaced_images(conf):
            cached = self.do_build(conf, context, stream, image_name="{0}-tester".format(conf_image_name))
        have_final = "{0}:latest".format(conf.image_name) in chain.from_iterable([image["RepoTags"] for image in conf.harpoon.docker_context.images()])

        provider_name = "{0}-provider".format(conf_image_name)
        provider_conf = conf.clone()
        provider_conf.name = "provider"
        provider_conf.image_name = provider_name
        provider_conf.container_id = None
        provider_conf.container_name = "{0}-intermediate-{1}".format(provider_name, str(uuid.uuid1())).replace("/", "__")

        with self.remove_replaced_images(provider_conf):
            if not have_final:
                log.info("Building first image for recursive image")
                with context.clone_with_new_dockerfile(conf, conf.recursive.make_first_dockerfile(conf.docker_file)) as new_context:
                    self.do_build(provider_conf, new_context, stream, image_name=provider_name)
                conf.harpoon.docker_context.tag(provider_name, conf.image_name, tag="latest", force=True)
            else:
                log.info("Building intermediate provider for recursive image")
                if not cached:
                    with context.clone_with_new_dockerfile(conf, conf.recursive.make_changed_dockerfile(conf.docker_file, conf.image_name)) as provider_context:
                        self.log_context_size(provider_context, provider_conf)
                        self.do_build(provider_conf, provider_context, stream, image_name=provider_name)
                else:
                    with conf.make_context(docker_file=conf.recursive.make_provider_dockerfile(conf.docker_file, conf.image_name)) as provider_context:
                        self.log_context_size(provider_context, provider_conf)
                        self.do_build(provider_conf, provider_context, stream, image_name=provider_name)
                        conf.from_name = conf.image_name
                        conf.image_name = provider_name
                        return

        builder_name = "{0}-for-commit".format(conf_image_name)
        builder_conf = conf.clone()

        builder_conf.image_name = builder_name
        builder_conf.container_id = None
        builder_conf.container_name = "{0}-intermediate-{1}".format(builder_name, str(uuid.uuid1())).replace("/", "__")
        builder_conf.volumes = Volumes(mount=[], share_with=[provider_conf])
        log.info("Building intermediate builder for recursive image")
        with self.remove_replaced_images(builder_conf):
            with context.clone_with_new_dockerfile(conf, conf.recursive.make_builder_dockerfile(conf.docker_file)) as provider_context:
                self.log_context_size(context, conf)
                self.do_build(builder_conf, provider_context, stream, image_name=builder_name)

        log.info("Running and committing builder container for recursive image")
        with self.remove_replaced_images(conf):
            Runner().run_container(builder_conf, {provider_conf.name:provider_conf, builder_conf.name:builder_conf}, detach=False, dependency=False, tag=conf.image_name)

        log.info("Building final provider of recursive image")
        with self.remove_replaced_images(provider_conf):
            with conf.make_context(docker_file=conf.recursive.make_provider_dockerfile(conf.docker_file, conf.image_name)) as provider_context:
                self.log_context_size(provider_context, provider_conf)
                self.do_build(provider_conf, provider_context, stream, image_name=provider_name)
        conf.from_name = conf.image_name
        conf.image_name = provider_name

