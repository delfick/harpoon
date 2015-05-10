#coding: spec

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.ship.builder import Builder

from tests.helpers import HarpoonCase

from input_algorithms.meta import Meta
from contextlib import contextmanager
import time
import uuid
import os

mtime = 1431170923

describe HarpoonCase, "Building docker images":
    def make_image(self, options):
        config_root = self.make_temp_dir()
        harpoon = HarpoonSpec().harpoon_spec.normalise(Meta({}, []), {"docker_context": self.docker_client})
        if "harpoon" not in options:
            options["harpoon"] = harpoon
        everything = {"harpoon": harpoon, "mtime": mtime, "_key_name_1": "awesome_image", "config_root": config_root}
        return HarpoonSpec().image_spec.normalise(Meta(everything, []), options)

    @contextmanager
    def a_built_image(self, options):
        ident = str(uuid.uuid1())
        ident_tag = "{0}:latest".format(ident)

        conf = self.make_image(options)
        conf.image_name = ident
        cached = Builder().build_image(conf)

        try:
            yield cached, conf
        finally:
            self.docker_client.remove_image(ident_tag)

    it "Builds an image":
        ident = str(uuid.uuid1())
        ident_tag = "{0}:latest".format(ident)

        images = self.docker_client.images()
        repo_tags = [image["RepoTags"] for image in images]
        assert all(ident_tag not in repo_tag_list for repo_tag_list in repo_tags), images

        conf = self.make_image({"context": False, "commands": ["FROM {0}".format(os.environ["BASE_IMAGE"])]})
        conf.image_name = ident
        Builder().build_image(conf)

        images = self.docker_client.images()
        repo_tags = [image["RepoTags"] for image in images]
        assert any(ident_tag in repo_tag_list for repo_tag_list in repo_tags), "Couldn't find {0} in {1}".format(ident_tag, images)

        self.docker_client.remove_image(ident_tag)

    it "knows if the build was cached":
        from_line = "FROM {0}".format(os.environ["BASE_IMAGE"])
        commands1 = [from_line]
        commands2 = [from_line, "RUN echo {0}".format(uuid.uuid1())]
        commands3 = commands2 + [["ADD", {"content": "blah", "dest": "/tmp/blah", "mtime": int(time.time())}]]
        with self.a_built_image({"context": False, "commands": commands1}) as (cached, conf1):
            assert cached

            with self.a_built_image({"context": False, "commands": commands2}) as (cached, conf2):
                assert not cached

                with self.a_built_image({"context": False, "commands": commands2}) as (cached, conf3):
                    assert cached

                    with self.a_built_image({"context": False, "commands": commands3}) as (cached, conf4):
                        assert not cached

