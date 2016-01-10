from input_algorithms.spec_base import NotSpecified
from contextlib import contextmanager
import docker.errors
import humanize
import logging
import os

log = logging.getLogger("harpoon.ship.builders.mixin")

class BuilderBase(object):
    def log_context_size(self, context, conf):
        context_size = humanize.naturalsize(os.stat(context.name).st_size)
        log.info("Building '%s' in '%s' with %s of context", conf.name, conf.context.parent_dir, context_size)

    @contextmanager
    def remove_replaced_images(self, conf):
        tag = "latest" if conf.tag is NotSpecified else conf.tag
        image_name = "{0}:{1}".format(conf.image_name, tag)

        current_ids = None
        if not conf.harpoon.keep_replaced:
            try:
                current_id = conf.harpoon.docker_context.inspect_image(image_name)["Id"]
            except docker.errors.APIError as error:
                if str(error).startswith("404 Client Error: Not Found"):
                    current_id = None
                else:
                    raise

        info = {"cached": False}
        yield info

        if current_id and not info.get("cached"):
            log.info("Looking for replaced images to remove")
            untagged = [image["Id"] for image in conf.harpoon.docker_context.images(filters={"dangling": True})]
            if current_id in untagged:
                log.info("Deleting replaced image\ttag=%s\told_hash=%s", "{0}".format(image_name), current_id)
                try:
                    conf.harpoon.docker_context.remove_image(current_id)
                except Exception as error:
                    log.error("Failed to remove replaced image\thash=%s\terror=%s", current_id, error)

