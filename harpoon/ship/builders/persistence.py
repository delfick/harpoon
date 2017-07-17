from harpoon.option_spec.image_objs import Volumes, Context
from harpoon.ship.builders.normal import NormalBuilder
from harpoon.ship.builders.base import BuilderBase
from harpoon.ship.runner import Runner

from docker.errors import APIError as DockerAPIError
from input_algorithms.spec_base import NotSpecified
from contextlib import contextmanager
import logging
import uuid
import sys
import six

log = logging.getLogger("harpoon.ship.builders.persistence")

class PersistenceBuilder(BuilderBase):
    def build(self, conf, context, stream):
        """Do a persistence build!"""
        existing_image = None

        # Find an existing image if it exists
        for image in conf.harpoon.docker_api.images():
            if image["RepoTags"]:
                if "{0}:latest".format(conf.image_name) in image["RepoTags"]:
                    existing_image = image['Id']

        # If we already have an image, then test to see if any of it's commands
        # have changed. If it's all still cached, then no need to remake the image!
        test_image_name = None
        if existing_image:
            log.info("Building test image for persistence image to see if the cache changed")
            cached, test_image_name = self.make_test_image(conf, context, stream)
            if cached:
                log.info("We have determined no change, so will just use existing image {0}".format(existing_image))
                return True

        try:
            self.make_image(conf, context, stream, existing_image)
        except Exception as error:
            exc_info = sys.exc_info()

            # Make sure if we fail that the test image doesn't
            # make a false positive the next time around
            # because failure means we almost certainly want to
            # go through this dance again
            try:
                if test_image_name:
                    conf.harpoon.docker_api.remove_image(test_image_name)
            except Exception as inner_error:
                log.exception(inner_error)

            six.reraise(*exc_info)

        # Image wasn't cached
        return False

    def make_test_image(self, conf, context, stream):
        docker_file = conf.persistence.make_test_dockerfile(conf.docker_file)
        with self.build_with_altered_context("tester", conf, context, stream, docker_file, tag=True) as (test_conf, cached):
            pass
        return cached, test_conf.image_name

    @contextmanager
    def build_with_altered_context(self, name, conf, context, stream, dockerfile, volumes_from=None, command=None, tag=False, volumes=None):
        new_conf = conf.clone()
        if name is not None:
            if tag:
                new_name = "{0}-{1}".format(conf.prefixed_image_name, name)
            else:
                new_name = None
            new_conf.name = name
            new_conf.image_name = new_name
            new_conf.volumes = volumes or Volumes([], [])
            new_conf.container_id = None
            new_conf.container_name = "{0}-{1}".format(new_name, str(uuid.uuid1())).replace("/", "__")
        else:
            new_name = conf.image_name

        new_conf.bash = NotSpecified
        new_conf.command = NotSpecified

        if command is not None:
            new_conf.bash = command

        # Do we share volumes?
        if volumes_from:
            new_conf.volumes = new_conf.volumes.clone()
            new_conf.volumes.share_with = list(conf.volumes.share_with) + volumes_from

        # Reuse the context or create new one depending on whether context was provided
        if context is not None:
            maker = context.clone_with_new_dockerfile(conf, dockerfile)
        else:
            new_conf.context = Context(enabled=False, parent_dir=new_conf.context.parent_dir)
            maker = new_conf.make_context(docker_file=dockerfile)

        # Create the context manager that removes replaced images
        # If we aren't tagging, then don't do that logic
        # Searching for the images takes time and I want to avoid that
        @contextmanager
        def remover(conf):
            yield
        if new_name is not None:
            remover = self.remove_replaced_images

        # Create our new image!
        with remover(new_conf):
            cached = False
            with maker as new_context:
                cached = NormalBuilder(new_name).build(new_conf, new_context, stream)
                new_conf.image_name = stream.current_container

        yield new_conf, cached

    def run_with_altered_context(self, name, conf, context, stream, dockerfile, volumes_from=None, tag=None, detach=False, command=None, volumes=None):
        """Helper to build and run a new dockerfile"""
        with self.build_with_altered_context(name, conf, context, stream, dockerfile, volumes_from=volumes_from, command=command, volumes=volumes) as (new_conf, _):

            # Hackity hack hakc hack hack hack
            # I should just be able to use conf.configuration["images"]
            # But it seems a bug in option_merge behaviour means the converters stop working :(
            # Much strange
            configuration = conf.configuration
            class Images(object):
                def __getitem__(self, key):
                    return configuration[["images", key]]
            images = Images()

            if detach:
                Runner().run_container(new_conf, images, detach=True, dependency=True)
            else:
                Runner().run_container(new_conf, images, detach=False, dependency=False, tag=True)
                new_conf.image_name = new_conf.committed

            return new_conf

    def make_image(self, conf, context, stream, existing_image):
        """
        If the image doesn't already exist, then we just run the normal docker_file
        commands followed by the action and we are done.

        Otherwise, we first create a container with a volume containing the folders from
        the existing container we want to persist. We then make a new image with the normal
        docker_file commands and run it in a container, copy over the folders from the VOLUME
        and commit into an image.

        Finally, we construct an image from that committed image and add a CMD command to
        the one specified in the options, or sh

        After all this we clean up everything, including that volume we created
        """
        if not existing_image:
            # Don't have an existing image to steal from
            # Just have to make it, no volumes or trickery involved!
            docker_file = conf.persistence.make_first_dockerfile(conf.docker_file)
            with self.build_with_altered_context(None, conf, context, stream, docker_file):
                pass

            # Make the test image so the next time we run this, it's already cached
            self.make_test_image(conf, context, stream)
            return

        # We have an existing image, let's steal from it!
        first_conf = None
        try:
            docker_file = conf.persistence.make_rerunner_prep_dockerfile(conf.docker_file, existing_image)
            volumes = conf.volumes
            if conf.persistence.no_volumes:
                volumes = None

            first_conf = self.run_with_altered_context("rerunner_prep"
                , conf, context, stream, docker_file, detach=True, command="while true; do sleep 5; done", volumes=volumes
                )
            log.info("Built {0}".format(first_conf.image_name))

            # Make the second image, which copies over from the VOLUME into the image
            docker_file = conf.persistence.make_second_dockerfile(conf.docker_file)
            second_image_conf = self.run_with_altered_context("second"
                , conf, context, stream, docker_file, volumes_from=[first_conf.container_id], volumes=volumes
                )

            log.info("Built {0}".format(second_image_conf.image_name))

            # Build the final image, which just appends the desired CMD to the end
            docker_file = conf.persistence.make_final_dockerfile(conf.docker_file, second_image_conf.image_name)
            with self.build_with_altered_context(None, conf, None, stream, docker_file, volumes=volumes):
                pass
        finally:
            if first_conf:
                Runner().stop_container(first_conf, remove_volumes=True)
                try:
                    conf.harpoon.docker_api.remove_image(first_conf.image_name)
                except DockerAPIError as error:
                    log.error(error)

