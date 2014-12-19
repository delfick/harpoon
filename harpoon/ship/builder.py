from harpoon.errors import NoSuchImage, BadCommand, FailedImage, UserQuit
from harpoon.ship.runner import Runner
from harpoon.layers import Layers

import humanize
import logging
import json
import sys
import os

log = logging.getLogger("harpoon.ship.builder")

class Builder(object):
    """Build an image from Image configuration"""

    def build_image(self, conf):
        """Build this image"""
        docker_lines = conf.commands.docker_file()
        with conf.context.make_context(conf.context.parent_dir, docker_lines, conf.mtime, silent_build=conf.harpoon.silent_build, extra_context=conf.commands.extra_context) as context:
            context_size = humanize.naturalsize(os.stat(context.name).st_size)
            log.info("Building '%s' in '%s' with %s of context", conf.name, conf.context.parent_dir, context_size)

            current_ids = None
            if not conf.harpoon.keep_replaced:
                images = conf.harpoon.docker_context.images()
                current_ids = [image["Id"] for image in images if "{0}:latest".format(conf.image_name) in image["RepoTags"]]

            buf = []
            cached = None
            last_line = ""
            current_hash = None
            try:
                for line in conf.harpoon.docker_context.build(fileobj=context, custom_context=True, tag=conf.image_name, stream=True, rm=True):
                    line_detail = None
                    try:
                        line_detail = json.loads(line)
                    except (ValueError, TypeError) as error:
                        log.warning("line from docker wasn't json", got=line, error=error)

                    if line_detail:
                        if "errorDetail" in line_detail:
                            raise FailedImage("Failed to build an image", image=conf.name, msg=line_detail["errorDetail"].get("message", line_detail["errorDetail"]))

                        if "stream" in line_detail:
                            line = line_detail["stream"]
                        elif "status" in line_detail:
                            line = line_detail["status"]
                            if line.startswith("Pulling image"):
                                if not line.endswith("\n"):
                                    line = "{0}\n".format(line)
                            else:
                                line = "\r{0}".format(line)

                        if last_line.strip() == "---> Using cache":
                            current_hash = line.split(" ", 1)[0].strip()
                        elif line.strip().startswith("---> Running in"):
                            current_hash = line[len("---> Running in "):].strip()

                    if line.strip().startswith("---> Running in"):
                        cached = False
                        buf.append(line)
                    elif line.strip().startswith("---> Using cache"):
                        cached = True

                    last_line = line
                    if cached is None:
                        if "already being pulled by another client" in line or "Pulling repository" in line:
                            cached = False
                        else:
                            buf.append(line)
                            continue

                    if not conf.harpoon.silent_build or not cached:
                        if buf:
                            for thing in buf:
                                sys.stdout.write(thing.encode('utf-8', 'replace'))
                                sys.stdout.flush()
                            buf = []

                        sys.stdout.write(line.encode('utf-8', 'replace'))
                        sys.stdout.flush()

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
            except (KeyboardInterrupt, Exception) as error:
                exc_info = sys.exc_info()
                if current_hash:
                    conf = type("Conf", (object, ), {"container_id": None, "container_name": current_hash, "harpoon": conf.harpoon})
                    conf.clone = lambda s: conf
                    with Runner().intervention(conf):
                        log.info("Removing bad container\thash=%s", current_hash)

                        try:
                            conf.harpoon.docker_context.kill(current_hash, signal=9)
                        except Exception as error:
                            log.error("Failed to kill dead container\thash=%s\terror=%s", current_hash, error)
                        try:
                            conf.harpoon.docker_context.remove_container(current_hash)
                        except Exception as error:
                            log.error("Failed to remove dead container\thash=%s\terror=%s", current_hash, error)

                if isinstance(error, KeyboardInterrupt):
                    raise UserQuit()
                else:
                    raise exc_info[1], None, exc_info[2]

    def make_image(self, conf, images, chain=None, made=None, ignore_deps=False):
        """Make us an image"""
        if chain is None:
            chain = []

        if made is None:
            made = {}

        if conf.name in made:
            return

        if conf.name in chain:
            raise BadCommand("Recursive FROM statements", chain=chain + [conf.name])

        if conf.name not in images:
            raise NoSuchImage(looking_for=conf.name, available=images.keys())

        if not ignore_deps:
            for dependency, image in conf.dependency_images():
                self.make_image(images[dependency], images, chain=chain + [conf.name], made=made)

        # Should have all our dependencies now
        log.info("Making image for '%s' (%s) - FROM %s", conf.name, conf.image_name, conf.commands.parent_image_name)
        self.build_image(conf)
        made[conf.name] = True

    def layered(self, images, only_pushable=False):
        """Yield layers of images"""
        if only_pushable:
            operate_on = dict((image, instance) for image, instance in images.items() if instance.image_index)
        else:
            operate_on = images

        layers = Layers(operate_on, all_images=images)
        layers.add_all_to_layers()
        return layers.layered

