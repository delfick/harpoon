# coding: spec

from tests.helpers import HarpoonCase

from harpoon.executor import docker_context as docker_context_maker

from delfick_project.errors_pytest import assertRaises
from docker.errors import ImageNotFound, NotFound
from contextlib import contextmanager
from textwrap import dedent
import subprocess
import requests
import pytest
import shlex
import time
import json
import os

pytestmark = pytest.mark.integration


def jsonloads(content):
    # In python3.5, json.loads can't take in bytes
    if isinstance(content, bytes):
        content = content.decode()
    return json.loads(content)


class Case(HarpoonCase):
    def make_harpoon(self, harpoon_options=None):
        if harpoon_options is None:
            harpoon_options = {}
        harpoon_options["docker_context"] = self.docker_client
        harpoon_options["docker_context_maker"] = docker_context_maker
        return HarpoonSpec().harpoon_spec.normalise(Meta.empty(), harpoon_options)

    @contextmanager
    def forwarded_port(self, port):
        if "CI_SERVER" in os.environ:
            yield
            return

        machine_name = os.environ["DOCKER_MACHINE_NAME"]
        p = subprocess.Popen(
            shlex.split(
                "docker-machine ssh {0} -N -L 0.0.0.0:{1}:127.0.0.1:{1}".format(machine_name, port)
            )
        )

        try:
            yield
        finally:
            p.kill()


# I'm putting this in it's own describe at the top so that it pulls in python:2
# Ready for the other tests. (this test is specifically that container_manager
# can pull in an image)
describe Case, "Container manager pulling":

    it "can pull in images", container_manager:
        try:
            self.docker_api.remove_image("python:2")
        except ImageNotFound:
            pass

        port = container_manager.free_port()

        config = dedent(
            """
        ---

        images:
          py:
            context: false
            commands:
              - FROM python:2
              - EXPOSE {port}
              - - ADD
                - dest: /a
                  content: "hello"
              - WORKDIR /
              - CMD python -m SimpleHTTPServer {port}

            wait_condition:
              command:
                - ss -tanp | grep {port}
        """.format(
                port=port
            )
        )

        info = container_manager.start(":{0}".format(port), port=port, config=config)
        res = requests.post(
            info["uri"]("/start_container"), json={"image": "py", "ports": [[0, port]]}
        )

        assert res.status_code == 200, res.content

        res = jsonloads(res.content)

        host_port = res["ports"][str(port)]
        container_id = res["container_id"]

        assert self.docker_api.inspect_container(container_id)["State"]["Running"]

        with self.forwarded_port(host_port):
            container_manager.wait_for_port(host_port)
            assert host_port != port, res.content
            assert requests.get("http://127.0.0.1:{0}/a".format(host_port)).content == b"hello"

        info["shutdown"]()
        with assertRaises(NotFound, r'404 Client Error: Not Found \("No such container:.+'):
            self.docker_api.inspect_container(container_id)

describe Case, "container_manager":

    it "can stop containers", container_manager:
        port = container_manager.free_port()

        config = dedent(
            """
        ---

        images:
          py:
            context: false
            commands:
              - FROM python:2
              - EXPOSE 4545
              - - ADD
                - dest: /a
                  content: "hello"
              - WORKDIR /
              - CMD python -m SimpleHTTPServer 4545

            wait_condition:
              command:
                - ss -tanp | grep 4545
        """
        )

        info = container_manager.start(":{0}".format(port), port=port, config=config)

        container_id = None

        # Do it twice and assert that the second container is different to the first
        for _ in range(2):
            res = requests.post(
                info["uri"]("/start_container"), json={"image": "py", "ports": [[0, 4545]]}
            )

            assert res.status_code == 200, res.content
            res = jsonloads(res.content)
            host_port = res["ports"]["4545"]
            assert container_id != res["container_id"]
            container_id = res["container_id"]

            assert self.docker_api.inspect_container(container_id)["State"]["Running"]

            with self.forwarded_port(host_port):
                container_manager.wait_for_port(host_port)
                assert host_port != port, res.content
                assert requests.get("http://127.0.0.1:{0}/a".format(host_port)).content == b"hello"

            res = requests.post(info["uri"]("/stop_container"), json={"image": "py"})
            assert res.status_code == 204, res.content

            with assertRaises(NotFound, r'404 Client Error: Not Found \("No such container:.+'):
                self.docker_api.inspect_container(container_id)

    it "returns the same container on subsequent starts", container_manager:
        port = container_manager.free_port()

        config = dedent(
            """
        ---

        images:
          py:
            context: false
            commands:
              - FROM python:2
              - EXPOSE 6789
              - - ADD
                - dest: /a
                  content: "hello"
              - WORKDIR /
              - CMD python -m SimpleHTTPServer 6789

            wait_condition:
              command:
                - ss -tanp | grep 6789
        """
        )

        info = container_manager.start(":{0}".format(port), port=port, config=config)

        res = requests.post(
            info["uri"]("/start_container"), json={"image": "py", "ports": [[0, 6789]]}
        )

        assert res.status_code == 200, res.content
        res = jsonloads(res.content)
        host_port = res["ports"]["6789"]
        container_id = res["container_id"]

        start = time.time()
        res = requests.post(
            info["uri"]("/start_container"), json={"image": "py", "ports": [[0, port]]}
        )
        assert time.time() - start < 1

        assert res.status_code == 200, res.content
        res = jsonloads(res.content)
        assert res["ports"]["6789"] == host_port
        assert container_id == res["container_id"]

    it "complains if the request is invalid", container_manager:
        port = container_manager.free_port()

        config = ""

        info = container_manager.start(":{0}".format(port), port=port, config=config)

        def assertError(res, content):
            assert res.status_code == 500
            assert res.headers["Content-Type"] == "application/json"
            assert jsonloads(res.content) == content

        res = requests.post(info["uri"]("/start_container"), json={"ports": [[0, 6789]]})
        assertError(
            res,
            {
                "error": {
                    "errors": [
                        {
                            "message": "Bad value. Expected a value but got none",
                            "meta": "{path=<request>.image}",
                        }
                    ],
                    "message": "Bad value",
                    "meta": "{path=<request>}",
                },
                "error_code": "BadSpecValue",
            },
        )

        res = requests.post(info["uri"]("/start_container"), json={"image": "py"})
        assertError(
            res,
            {
                "error": {
                    "errors": [
                        {
                            "message": "Bad value. Expected a value but got none",
                            "meta": "{path=<request>.ports}",
                        }
                    ],
                    "message": "Bad value",
                    "meta": "{path=<request>}",
                },
                "error_code": "BadSpecValue",
            },
        )

        res = requests.post(
            info["uri"]("/start_container"), json={"image": "py", "ports": [[0, 6789]]}
        )
        assertError(
            res,
            {
                "error": {"available": [], "message": "Couldn't find image", "wanted": "py"},
                "error_code": "NoSuchImage",
            },
        )
