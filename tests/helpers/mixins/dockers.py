from harpoon.executor import docker_context
from harpoon.ship.builder import Builder

from contextlib import contextmanager
import docker.errors
import uuid

info = {}


class DockersAssertionsMixin:
    @property
    def docker_client(self):
        if "docker_client" not in info:
            info["docker_client"] = docker_context()
        return info["docker_client"]

    @property
    def docker_api(self):
        return self.docker_client.api

    def refresh_docker_client(self):
        if "docker_client" in info:
            del info["docker_client"]

    def new_docker_client(self):
        self.refresh_docker_client()
        return self.docker_client

    @contextmanager
    def a_built_image(self, options, harpoon_options=None, images=None, **kwargs):
        ident = str(uuid.uuid1())
        ident_tag = "{0}:latest".format(ident)

        conf = self.make_image(options, harpoon_options, **kwargs)
        if images:
            images[conf.image_name] = conf
        conf.image_name = ident

        if images:
            images[conf.image_name] = conf
            cached = Builder().make_image(conf, images)
        else:
            cached = Builder().build_image(conf)

        try:
            yield cached, conf
        finally:
            try:
                self.docker_api.remove_image(ident_tag)
            except docker.errors.APIError as error:
                print("Failed to delete the image", error)
