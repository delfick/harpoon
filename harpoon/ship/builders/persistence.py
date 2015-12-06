from harpoon.ship.builders.base import BuilderBase
from harpoon.option_spec.image_objs import Volumes
from harpoon.ship.runner import Runner

from input_algorithms.spec_base import NotSpecified
from itertools import chain
import logging
import uuid

log = logging.getLogger("harpoon.ship.builders.persistence")

class RecursiveBuild(BuildBase):
    def do_recursive_build(self, conf, context, stream, needs_provider=False):
        """Do a recursive build!"""
        conf_image_name = conf.name
        if conf.image_name_prefix not in (NotSpecified, "", None):
            conf_image_name = "{0}-{1}".format(conf.image_name_prefix, conf.name)

        test_conf = conf.clone()
        test_conf.image_name = "{0}-tester".format(conf_image_name)
        log.info("Building test image for recursive image to see if the cache changed")
        with self.remove_replaced_images(test_conf) as info:
            cached = self.do_build(test_conf, context, stream)
            info['cached'] = cached

        have_final = "{0}:latest".format(conf.image_name) in chain.from_iterable([image["RepoTags"] for image in conf.harpoon.docker_context.images()])

        provider_name = "{0}-provider".format(conf_image_name)
        provider_conf = conf.clone()
        provider_conf.name = "provider"
        provider_conf.image_name = provider_name
        provider_conf.container_id = None
        provider_conf.container_name = "{0}-intermediate-{1}".format(provider_name, str(uuid.uuid1())).replace("/", "__")
        provider_conf.bash = NotSpecified
        provider_conf.command = NotSpecified

        if not have_final:
            log.info("Building first image for recursive image")
            with context.clone_with_new_dockerfile(conf, conf.recursive.make_first_dockerfile(conf.docker_file)) as new_context:
                self.do_build(conf, new_context, stream)

        if not needs_provider and cached:
            return cached

        with self.remove_replaced_images(provider_conf) as info:
            if cached:
                with conf.make_context(docker_file=conf.recursive.make_provider_dockerfile(conf.docker_file, conf.image_name)) as provider_context:
                    self.log_context_size(provider_context, provider_conf)
                    info['cached'] = self.do_build(provider_conf, provider_context, stream, image_name=provider_name)
                    conf.from_name = conf.image_name
                    conf.image_name = provider_name
                    conf.deleteable = True
                    return cached
            else:
                log.info("Building intermediate provider for recursive image")
                with context.clone_with_new_dockerfile(conf, conf.recursive.make_changed_dockerfile(conf.docker_file, conf.image_name)) as provider_context:
                    self.log_context_size(provider_context, provider_conf)
                    self.do_build(provider_conf, provider_context, stream, image_name=provider_name)

        builder_name = "{0}-for-commit".format(conf_image_name)
        builder_conf = conf.clone()

        builder_conf.image_name = builder_name
        builder_conf.container_id = None
        builder_conf.container_name = "{0}-intermediate-{1}".format(builder_name, str(uuid.uuid1())).replace("/", "__")
        builder_conf.volumes = Volumes(mount=[], share_with=[provider_conf])
        builder_conf.bash = NotSpecified
        builder_conf.command = NotSpecified
        log.info("Building intermediate builder for recursive image")
        with self.remove_replaced_images(builder_conf) as info:
            with context.clone_with_new_dockerfile(conf, conf.recursive.make_builder_dockerfile(conf.docker_file)) as builder_context:
                self.log_context_size(builder_context, builder_conf)
                info['cached'] = self.do_build(builder_conf, builder_context, stream, image_name=builder_name)

        log.info("Running and committing builder container for recursive image")
        with self.remove_replaced_images(conf):
            Runner().run_container(builder_conf, {provider_conf.name:provider_conf, builder_conf.name:builder_conf}, detach=False, dependency=False, tag=conf.image_name)

        log.info("Removing intermediate image %s", builder_conf.image_name)
        conf.harpoon.docker_context.remove_image(builder_conf.image_name)

        if not needs_provider:
            return cached

        log.info("Building final provider of recursive image")
        with self.remove_replaced_images(provider_conf) as info:
            with conf.make_context(docker_file=conf.recursive.make_provider_dockerfile(conf.docker_file, conf.image_name)) as provider_context:
                self.log_context_size(provider_context, provider_conf)
                info['cached'] = self.do_build(provider_conf, provider_context, stream, image_name=provider_name)

        conf.from_name = conf.image_name
        conf.image_name = provider_name
        conf.deleteable = True
        return cached

