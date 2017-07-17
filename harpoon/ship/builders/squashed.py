from harpoon.errors import BadEnvironment, HarpoonError
from harpoon.ship.builders.normal import NormalBuilder
from harpoon.option_spec.image_objs import DockerFile
from harpoon.ship.builders.base import BuilderBase
from harpoon import helpers as hp

from input_algorithms.spec_base import NotSpecified
from delfick_app import command_output
import logging

log = logging.getLogger("harpoon.ship.builders.squashed")

def SquashedBuilder(BuilderBase):
    def __init__(self, squash_commands):
        self.squash_commands = squash_commands

    def build(self, conf, context, stream):
        """Do a squash build"""
        squashing = conf
        output, status = command_output("which docker-squash")
        if status != 0:
            raise BadEnvironment("Please put docker-squash in your PATH first: https://github.com/jwilder/docker-squash")

        if self.squash_commands:
            squasher_conf = conf.clone()
            squasher_conf.image_name = "{0}-for-squashing".format(conf.name)
            if conf.image_name_prefix not in ("", None, NotSpecified):
                squasher.conf.image_name = "{0}-{1}".format(conf.image_name_prefix, squasher_conf.image_name)

            with self.remove_replaced_images(squasher_conf) as info:
                original_docker_file = conf.docker_file
                new_docker_file = DockerFile(["FROM {0}".format(conf.image_name)] + self.squash_commands, original_docker_file.mtime)
                with context.clone_with_new_dockerfile(squasher_conf, new_docker_file) as squasher_context:
                    info['cached'] = NormalBuilder().build(squasher_conf, squasher_context, stream)
            squashing = squasher_conf

        log.info("Saving image\timage=%s", squashing.image_name)
        with hp.a_temp_file() as fle:
            res = conf.harpoon.docker_api.get_image(squashing.image_name)
            fle.write(res.read())
            fle.close()

            with hp.a_temp_file() as fle2:
                output, status = command_output("sudo docker-squash -i {0} -o {1} -t {2} -verbose".format(fle.name, fle2.name, conf.image_name), verbose=True, timeout=600)
                if status != 0:
                    raise HarpoonError("Failed to squash the image!")

                output, status = command_output("docker load", stdin=open(fle2.name), verbose=True, timeout=600)
                if status != 0:
                    raise HarpoonError("Failed to load the squashed image")

        if squashing is not conf:
            log.info("Removing intermediate image %s", squashing.image_name)
            conf.harpoon.docker_api.remove_image(squashing.image_name)

