"""
The Builder is responsible for finding and building docker images in
the correct order

Building an image requires building all dependent images, creating the necessary
context, and actually building the current image.
"""

from harpoon.errors import NoSuchImage, BadCommand, UserQuit
from harpoon.ship.progress_stream import ProgressStream
from harpoon.ship.builders.normal import NormalBuilder
from harpoon.ship.builders.base import BuilderBase
from harpoon.ship.runner import Runner

from delfick_project.layerz import Layers
import logging
import sys

log = logging.getLogger("harpoon.ship.builder")

########################
###   PROGRESS STREAM
########################


class BuildProgressStream(ProgressStream):
    def setup(self):
        self.last_line = ""
        self.current_action = ""
        self.current_container = None
        self.last_created_image = None
        self.intermediate_images = []

    def interpret_line(self, line_detail):
        if "stream" in line_detail:
            if line_detail["stream"].strip() == "":
                self.add_line(line_detail["stream"])
                return

            self.interpret_stream(line_detail["stream"])
            self.last_line = line_detail["stream"]
        elif "status" in line_detail:
            self.interpret_status(line_detail["status"])
            self.last_line = line_detail["status"]
        elif "aux" in line_detail:
            log.info("Created image\t%s", line_detail["aux"].get("ID", ""))
        else:
            self.interpret_unknown(line_detail)
            self.last_line = str(line_detail)

    def interpret_stream(self, line):
        stripped = line.strip()
        if stripped.startswith("--->") and " " in stripped:
            self.last_created_image = stripped.split(" ", 1)[1]

        if line.startswith("Step "):
            action = line[line.find(":") + 1 :].strip()
            self.current_action = action[: action.find(" ")].strip()
            if self.current_action == "FROM" and self.last_created_image:
                self.intermediate_images.append(self.last_created_image)

            self.last_created_image = None

        if line.strip().startswith("---> Running in"):
            self.current_container = line[len("---> Running in ") :].strip()
        elif line.strip().startswith("Successfully built"):
            self.current_container = line[len("Successfully built") :].strip()
            self.last_created_image = None

        if self.last_line.startswith("Step ") and line.strip().startswith("---> "):
            if self.current_action == "FROM":
                self.cached = True
            else:
                self.cached = False

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


class Builder(BuilderBase):
    """Build an image from Image configuration"""

    def make_image(
        self,
        conf,
        images,
        chain=None,
        parent_chain=None,
        made=None,
        ignore_deps=False,
        ignore_parent=False,
        pushing=False,
    ):
        """Make us an image"""
        made = {} if made is None else made
        chain = [] if chain is None else chain
        parent_chain = [] if parent_chain is None else parent_chain

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
                self.make_image(
                    images[dependency],
                    images,
                    chain=chain + [conf.name],
                    made=made,
                    pushing=pushing,
                )

        if not ignore_parent:
            for dep in conf.commands.dependent_images:
                if not isinstance(dep, str):
                    self.make_image(
                        dep, images, chain, parent_chain + [conf.name], made=made, pushing=pushing
                    )

        # Should have all our dependencies now
        log.info("Making image for '%s' (%s)", conf.name, conf.image_name)
        cached = self.build_image(conf, pushing=pushing)
        made[conf.name] = True
        return cached

    def build_image(self, conf, pushing=False):
        """Build this image"""
        with conf.make_context() as context:
            try:
                stream = BuildProgressStream(conf.harpoon.silent_build)
                with self.remove_replaced_images(conf) as info:
                    cached = NormalBuilder().build(conf, context, stream)
                    info["cached"] = cached
            except (KeyboardInterrupt, Exception) as error:
                exc_info = sys.exc_info()
                if stream.current_container:
                    Runner().stage_build_intervention(conf, stream.current_container)

                if isinstance(error, KeyboardInterrupt):
                    raise UserQuit()
                else:
                    exc_info[1].__traceback__ = exc_info[2]
                    raise exc_info[1]
            finally:
                if stream and stream.intermediate_images and conf.cleanup_intermediate_images:
                    for image in stream.intermediate_images:
                        log.info("Deleting intermediate image\timage=%s", image)
                        try:
                            conf.harpoon.docker_api.remove_image(image)
                        except Exception as error:
                            log.error(
                                "Failed to remove intermediate image\timage=%s\terror=%s",
                                image,
                                error,
                            )

        return cached

    def layered(self, images, only_pushable=False):
        """Yield layers of images"""
        if only_pushable:
            operate_on = dict(
                (image, instance) for image, instance in images.items() if instance.image_index
            )
        else:
            operate_on = images

        layers = Layers(operate_on, all_deps=images)
        layers.add_all_to_layers()
        for layer in layers.layered:
            buf = []
            for image_name, image in layer:
                if image.image_index:
                    buf.append((image_name, image))
            if buf:
                yield buf
