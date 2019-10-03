# coding: spec

from harpoon.errors import FailedImage, BadImage, AlreadyBoundPorts, ProgrammerError
from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.ship.runner import Runner

from tests.helpers import HarpoonCase

from delfick_project.option_merge import Converter, MergedOptions
from delfick_project.norms import sb, Meta
from contextlib import contextmanager
from unittest import mock
import logging
import socket
import codecs
import pytest
import os
import re

pytestmark = pytest.mark.integration

log = logging.getLogger("tests.docker.test_docker_run")

describe HarpoonCase, "Building docker images":

    def make_image(self, options, harpoon_options=None, harpoon=None):
        config_root = self.make_temp_dir()
        if harpoon_options is None and harpoon is None:
            harpoon_options = {}

        if harpoon_options is not None:
            harpoon_options["docker_context"] = self.docker_client
            harpoon_options["docker_context_maker"] = self.new_docker_client
        elif harpoon:
            if harpoon.docker_context is sb.NotSpecified:
                harpoon.docker_context = self.docker_client
            if harpoon.docker_context_maker is sb.NotSpecified:
                harpoon.docker_context_maker = self.new_docker_client

        if harpoon_options and harpoon:
            raise ProgrammerError("Please only specify one of harpoon_options and harpoon")

        if harpoon is None:
            harpoon = HarpoonSpec().harpoon_spec.normalise(Meta({}, []), harpoon_options)

        if "harpoon" not in options:
            options["harpoon"] = harpoon

        everything = MergedOptions.using(
            {"harpoon": harpoon, "_key_name_1": "awesome_image", "config_root": config_root}
        )

        harpoon_converter = Converter(convert=lambda *args: harpoon, convert_path=["harpoon"])
        everything.add_converter(harpoon_converter)
        everything.converters.activate()

        if "configuration" not in options:
            options["configuration"] = everything
        return HarpoonSpec().image_spec.normalise(Meta(everything, []), options)

    @contextmanager
    def a_port(self, port):
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("localhost", port))
            s.listen(1)

            yield
        finally:
            try:
                if s is not None:
                    s.close()
            except Exception as error:
                log.warning(error)

    it "can complain if ports are already bound to something else":
        if self.docker_api.base_url.startswith("http"):
            pytest.skip("docker api is http based")

        commands = ["FROM {0}".format(os.environ["BASE_IMAGE"]), "CMD exit 1"]

        fake_sys_stdout = self.make_temp_file()
        fake_sys_stderr = self.make_temp_file()

        with self.a_port(9999):
            with self.a_port(9998):
                with self.fuzzyAssertRaisesError(AlreadyBoundPorts, ports=[9999, 9998]):
                    with self.a_built_image(
                        {
                            "context": False,
                            "commands": commands,
                            "ports": ["9999:9999", "9998:9998"],
                        },
                        {
                            "no_intervention": True,
                            "stdout": fake_sys_stdout,
                            "tty_stdout": fake_sys_stdout,
                            "tty_stderr": fake_sys_stderr,
                        },
                    ) as (cached, conf):
                        Runner().run_container(conf, {conf.name: conf})

    it "does not complain if nothing is using a port":
        if self.docker_api.base_url.startswith("http"):
            pytest.skip("docker api is http based")

        commands = ["FROM {0}".format(os.environ["BASE_IMAGE"]), "CMD exit 0"]

        fake_sys_stdout = self.make_temp_file()
        fake_sys_stderr = self.make_temp_file()

        # Make sure we can get 9999
        with self.a_port(9999):
            pass

        with self.a_built_image(
            {"context": False, "commands": commands, "ports": ["9999:9999"]},
            {
                "no_intervention": True,
                "stdout": fake_sys_stdout,
                "tty_stdout": fake_sys_stdout,
                "tty_stderr": fake_sys_stderr,
            },
        ) as (cached, conf):
            Runner().run_container(conf, {conf.name: conf})

        assert True

    it "can has links":
        commands1 = [
            "FROM python:3",
            "EXPOSE 8000",
            "RUN echo hi1 > /one",
            "CMD python -m http.server",
        ]

        commands2 = [
            "FROM python:3",
            "EXPOSE 8000",
            "RUN echo there2 > /two",
            "CMD python -m http.server",
        ]

        commands3 = [
            "FROM python:3",
            "CMD sleep 1 && curl http://one:8000/one && curl http://two:8000/two",
        ]

        fake_sys_stdout = self.make_temp_file()
        fake_sys_stderr = self.make_temp_file()

        harpoon_options = {
            "no_intervention": True,
            "stdout": fake_sys_stdout,
            "tty_stdout": fake_sys_stdout,
            "tty_stderr": fake_sys_stderr,
        }
        harpoon = HarpoonSpec().harpoon_spec.normalise(Meta({}, []), harpoon_options)

        with self.a_built_image(
            {"name": "one", "context": False, "commands": commands1}, harpoon=harpoon
        ) as (_, conf1):
            assert len(conf1.harpoon.docker_context.networks.list()) == 3
            links = [[conf1, "one"]]
            with self.a_built_image(
                {"name": "two", "links": links, "context": False, "commands": commands2},
                harpoon=harpoon,
            ) as (_, conf2):
                links = [[conf1, "one"], [conf2, "two"]]
                with self.a_built_image(
                    {"name": "three", "context": False, "commands": commands3, "links": links},
                    harpoon=harpoon,
                ) as (_, conf3):
                    Runner().run_container(
                        conf3, {conf1.name: conf1, conf2.name: conf2, conf3.name: conf3}
                    )
        assert len(conf3.harpoon.docker_context.networks.list()) == 3

        with open(fake_sys_stdout.name) as fle:
            output = fle.read().strip()

        if isinstance(output, bytes):
            output = output.decode("utf-8")
        output = [line.strip() for line in output.split("\n") if "lxc-start" not in line]

        assert output[-2:] == ["hi1", "there2"]

    it "can intervene a broken build":
        called = []
        original_commit_and_run = Runner.commit_and_run

        def commit_and_run(*args, **kwargs):
            kwargs["command"] = "echo 'intervention_goes_here'"
            called.append("commit_and_run")
            return original_commit_and_run(Runner(), *args, **kwargs)

        fake_commit_and_run = mock.Mock(name="commit_and_run", side_effect=commit_and_run)

        commands = ["FROM {0}".format(os.environ["BASE_IMAGE"]), "RUN exit 1"]

        try:
            fake_sys_stdout = self.make_temp_file()
            fake_sys_stderr = self.make_temp_file()
            with mock.patch("harpoon.ship.builder.Runner.commit_and_run", fake_commit_and_run):
                with mock.patch.dict(__builtins__, input=lambda *args: "y\n"):
                    with self.a_built_image(
                        {"context": False, "commands": commands},
                        {
                            "stdout": fake_sys_stdout,
                            "tty_stdout": fake_sys_stdout,
                            "tty_stderr": fake_sys_stderr,
                        },
                    ) as (cached, conf):
                        pass
        except FailedImage as error:
            expected = re.compile(
                r"The command [\[']/bin/sh -c exit 1[\]'] returned a non-zero code: 1"
            )
            assert expected.match(str(error.kwargs["msg"])), "Expected {0} to match {1}".format(
                str(error.kwargs["msg"]), expected.pattern
            )
            assert error.kwargs["image"] == "awesome_image"

        assert called == ["commit_and_run"]

        with open(fake_sys_stdout.name) as fle:
            output = fle.read().strip()

        if isinstance(output, bytes):
            output = output.decode("utf-8")
        output = "\n".join([line for line in output.split("\n") if "lxc-start" not in line])

        expected = """
         Step 1(/2)? : FROM busybox:buildroot-2014.02
          ---> [a-zA-Z0-9]{12}
         Step 2(/2)? : RUN exit 1
          ---> Running in .+
         !!!!
         It would appear building the image failed
         Do you want to run /bin/bash where the build to help debug why it failed?
         intervention_goes_here
        """

        self.assertReMatchLines(
            expected,
            output,
            remove=[
                re.compile("^Successfully tagged .+"),
                re.compile("^Removing intermediate container .+"),
            ],
        )

    it "can intervene a broken container":
        called = []
        original_commit_and_run = Runner.commit_and_run

        def commit_and_run(*args, **kwargs):
            kwargs["command"] = "echo 'intervention_goes_here'"
            called.append("commit_and_run")
            return original_commit_and_run(Runner(), *args, **kwargs)

        fake_commit_and_run = mock.Mock(name="commit_and_run", side_effect=commit_and_run)

        commands = ["FROM {0}".format(os.environ["BASE_IMAGE"]), "CMD sh -c 'exit 1'"]

        try:
            fake_sys_stdout = self.make_temp_file()
            fake_sys_stderr = self.make_temp_file()
            with mock.patch("harpoon.ship.builder.Runner.commit_and_run", fake_commit_and_run):
                with mock.patch.dict(__builtins__, input=lambda *args: "y\n"):
                    with self.a_built_image(
                        {"context": False, "commands": commands},
                        {
                            "stdout": fake_sys_stdout,
                            "tty_stdout": fake_sys_stdout,
                            "tty_stderr": fake_sys_stderr,
                        },
                    ) as (cached, conf):
                        Runner().run_container(conf, {conf.name: conf})
        except BadImage as error:
            assert "Failed to run container" in str(error)

        assert called == ["commit_and_run"]

        with codecs.open(fake_sys_stdout.name) as fle:
            output = fle.read().strip()

        if isinstance(output, bytes):
            output = output.decode("utf-8")
        output = "\n".join([line for line in output.split("\n") if "lxc-start" not in line])

        expected = """
         Step 1(/2)? : FROM busybox:buildroot-2014.02
          ---> [a-zA-Z0-9]{12}
         Step 2(/2)? : CMD ['sh', '-c', 'exit 1']
          ---> Running in .+
          --->
         Successfully built .+
         !!!!
         Failed to run the container!
         Do you want commit the container in it's current state and /bin/bash into it to debug?
         intervention_goes_here
        """

        self.assertReMatchLines(
            expected,
            output,
            remove=[
                re.compile("^Successfully tagged .+"),
                re.compile("^Removing intermediate container .+"),
            ],
        )

    it "can intervene a broken container with the tty starting":
        called = []
        original_commit_and_run = Runner.commit_and_run

        def commit_and_run(*args, **kwargs):
            kwargs["command"] = "echo 'intervention_goes_here'"
            called.append("commit_and_run")
            return original_commit_and_run(Runner(), *args, **kwargs)

        fake_commit_and_run = mock.Mock(name="commit_and_run", side_effect=commit_and_run)

        commands = [
            "FROM {0}".format(os.environ["BASE_IMAGE"]),
            """CMD echo 'hi'; sleep 1; exit 1""",
        ]

        try:
            fake_sys_stdout = self.make_temp_file()
            fake_sys_stderr = self.make_temp_file()
            with mock.patch("harpoon.ship.builder.Runner.commit_and_run", fake_commit_and_run):
                with mock.patch.dict(__builtins__, input=lambda *args: "y\n"):
                    with self.a_built_image(
                        {"context": False, "commands": commands},
                        {
                            "stdout": fake_sys_stdout,
                            "tty_stdout": fake_sys_stdout,
                            "tty_stderr": fake_sys_stderr,
                        },
                    ) as (cached, conf):
                        Runner().run_container(conf, {conf.name: conf})
        except BadImage as error:
            print(error)
            assert "Failed to run container" in str(error)

        assert called == ["commit_and_run"]

        with codecs.open(fake_sys_stdout.name) as fle:
            output = fle.read().strip()

        if isinstance(output, bytes):
            output = output.decode("utf-8")
        output = "\n".join([line for line in output.split("\n") if "lxc-start" not in line])

        expected = """
         Step 1(/2)? : FROM busybox:buildroot-2014.02
          ---> [a-zA-Z0-9]{12}
         Step 2(/2)? : CMD echo 'hi'; sleep 1; exit 1
          ---> Running in .+
          ---> .+
         Successfully built .+
         hi
         !!!!
         Failed to run the container!
         Do you want commit the container in it's current state and /bin/bash into it to debug?
         intervention_goes_here
        """

        self.assertReMatchLines(
            expected,
            output,
            remove=[
                re.compile("^Successfully tagged .+"),
                re.compile("^Removing intermediate container .+"),
            ],
        )
