from harpoon.ship.progress_stream import Failure, Unknown
from harpoon.ship.builders.base import BuilderBase
from harpoon.errors import FailedImage
from harpoon import helpers as hp

from itertools import chain
import logging
import six

log = logging.getLogger("harpoon.ship.builders.normal")

class NormalBuilder(BuilderBase):
    def __init__(self, image_name=None):
        self.image_name = image_name

    def build(self, conf, context, stream):
        image_name = self.image_name
        if image_name is None:
            image_name = conf.image_name_with_tag

        context.close()
        self.log_context_size(context, conf)

        # Login into the correct registry
        current_tags = list(chain.from_iterable(image["RepoTags"] for image in conf.harpoon.docker_api.images() if image["RepoTags"]))

        for dep in conf.commands.dependent_images:
            if isinstance(dep, six.string_types):
                if ":" not in dep:
                    dep = "{0}:latest".format(dep)

                if dep not in current_tags:
                    conf.login(dep, is_pushing=False)

        cache_from = list(conf.cache_from_names)
        if cache_from:
            log.info("Using cache from the following images\timages={0}".format(", ".join(cache_from)))

        lines = conf.harpoon.docker_api.build(
              tag = image_name
            , fileobj = context.tmpfile
            , custom_context = True
            , cache_from = list(conf.cache_from_names)

            , rm = True
            , pull = False
            )

        for found in lines:
            for line in found.decode().split("\n"):
                if line.strip():
                    try:
                        stream.feed(line.encode())
                    except Failure as error:
                        raise FailedImage("Failed to build an image", image=conf.name, msg=error)
                    except Unknown as error:
                        log.warning("Unknown line\tline=%s", error)

                    for part in stream.printable():
                        hp.write_to(conf.harpoon.stdout, part)
                    conf.harpoon.stdout.flush()

        return stream.cached

