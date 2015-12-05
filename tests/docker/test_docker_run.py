#coding: spec

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.errors import FailedImage, BadImage
from harpoon.ship.runner import Runner

from tests.helpers import HarpoonCase

from option_merge.converter import Converter
from option_merge import MergedOptions
from input_algorithms.meta import Meta
import codecs
import nose
import mock
import six
import os
import re

mtime = 1431170923

describe HarpoonCase, "Building docker images":
    def make_image(self, options, harpoon_options=None):
        config_root = self.make_temp_dir()
        if harpoon_options is None:
            harpoon_options = {}
        harpoon_options["docker_context"] = self.docker_client
        harpoon_options["docker_context_maker"] = self.new_docker_client

        harpoon = HarpoonSpec().harpoon_spec.normalise(Meta({}, []), harpoon_options)
        if "harpoon" not in options:
            options["harpoon"] = harpoon

        everything = MergedOptions.using({"harpoon": harpoon, "mtime": mtime, "_key_name_1": "awesome_image", "config_root": config_root})

        harpoon_converter = Converter(convert=lambda *args: harpoon, convert_path=["harpoon"])
        everything.add_converter(harpoon_converter)
        everything.converters.activate()

        if "configuration" not in options:
            options["configuration"] = everything
        return HarpoonSpec().image_spec.normalise(Meta(everything, []), options)

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
                with mock.patch("harpoon.ship.runner.input", lambda *args: 'y\n'):
                    with self.a_built_image({"context": False, "commands": commands}, {"stdout": fake_sys_stdout, "tty_stdout": fake_sys_stdout, "tty_stderr": fake_sys_stderr}) as (cached, conf):
                        pass
        except FailedImage as error:
            expected = re.compile("The command [\[']/bin/sh -c exit 1[\]'] returned a non-zero code: 1")
            assert expected.match(str(error.kwargs["msg"])), "Expected {0} to match {1}".format(str(error.kwargs["msg"]), expected.pattern)
            self.assertEqual(error.kwargs["image"], "awesome_image")

        self.assertEqual(called, ["commit_and_run"])

        with open(fake_sys_stdout.name) as fle:
            output = fle.read().strip()

        if isinstance(output, six.binary_type):
            output = output.decode('utf-8')
        output = '\n'.join([line for line in output.split('\n') if "lxc-start" not in line])

        expected = """
         Step 1 : FROM busybox:buildroot-2014.02
          ---> [a-zA-Z0-9]{12}
         Step 2 : RUN exit 1
          ---> Running in .+
         !!!!
         It would appear building the image failed
         Do you want to run /bin/bash where the build to help debug why it failed?
         intervention_goes_here
        """

        self.assertReMatchLines(expected, output)

    it "can intervene a broken container":
        called = []
        original_commit_and_run = Runner.commit_and_run
        def commit_and_run(*args, **kwargs):
            kwargs["command"] = "echo 'intervention_goes_here'"
            called.append("commit_and_run")
            return original_commit_and_run(Runner(), *args, **kwargs)
        fake_commit_and_run = mock.Mock(name="commit_and_run", side_effect=commit_and_run)

        commands = ["FROM {0}".format(os.environ["BASE_IMAGE"]), "CMD /bin/sh -c 'exit 1'"]

        try:
            fake_sys_stdout = self.make_temp_file()
            fake_sys_stderr = self.make_temp_file()
            with mock.patch("harpoon.ship.builder.Runner.commit_and_run", fake_commit_and_run):
                with mock.patch("harpoon.ship.runner.input", lambda *args: 'y\n'):
                    with self.a_built_image({"context": False, "commands": commands}, {"stdout": fake_sys_stdout, "tty_stdout": fake_sys_stdout, "tty_stderr": fake_sys_stderr}) as (cached, conf):
                        Runner().run_container(conf, {conf.name: conf})
        except BadImage as error:
            assert "Failed to run container" in str(error)

        self.assertEqual(called, ["commit_and_run"])

        with codecs.open(fake_sys_stdout.name) as fle:
            output = fle.read().strip()

        if isinstance(output, six.binary_type):
            output = output.decode('utf-8')
        output = '\n'.join([line for line in output.split('\n') if "lxc-start" not in line])

        expected = """
         Step 1 : FROM busybox:buildroot-2014.02
          ---> [a-zA-Z0-9]{12}
         Step 2 : CMD ['/bin/sh', '-c', 'exit 1']
          ---> Running in .+
          --->
         Removing intermediate container .+
         Successfully built .+
         !!!!
         Failed to run the container!
         Do you want commit the container in it's current state and /bin/bash into it to debug?
         intervention_goes_here
        """

        self.assertReMatchLines(expected, output)

    it "can intervene a broken container with the tty starting":
        called = []
        original_commit_and_run = Runner.commit_and_run
        def commit_and_run(*args, **kwargs):
            kwargs["command"] = "echo 'intervention_goes_here'"
            called.append("commit_and_run")
            return original_commit_and_run(Runner(), *args, **kwargs)
        fake_commit_and_run = mock.Mock(name="commit_and_run", side_effect=commit_and_run)

        commands = ["FROM {0}".format(os.environ["BASE_IMAGE"]), '''CMD echo 'hi'; sleep 1; exit 1''']

        try:
            fake_sys_stdout = self.make_temp_file()
            fake_sys_stderr = self.make_temp_file()
            with mock.patch("harpoon.ship.builder.Runner.commit_and_run", fake_commit_and_run):
                with mock.patch("harpoon.ship.runner.input", lambda *args: 'y\n'):
                    with self.a_built_image({"context": False, "commands": commands}, {"stdout": fake_sys_stdout, "tty_stdout": fake_sys_stdout, "tty_stderr": fake_sys_stderr}) as (cached, conf):
                        Runner().run_container(conf, {conf.name: conf})
        except BadImage as error:
            print(error)
            assert "Failed to run container" in str(error)

        self.assertEqual(called, ["commit_and_run"])

        with codecs.open(fake_sys_stdout.name) as fle:
            output = fle.read().strip()

        if isinstance(output, six.binary_type):
            output = output.decode('utf-8')
        output = '\n'.join([line for line in output.split('\n') if "lxc-start" not in line])

        expected = """
         Step 1 : FROM busybox:buildroot-2014.02
          ---> [a-zA-Z0-9]{12}
         Step 2 : CMD echo 'hi'; sleep 1; exit 1
          ---> Running in .+
          ---> .+
         Removing intermediate container .+
         Successfully built .+
         hi
         !!!!
         Failed to run the container!
         Do you want commit the container in it's current state and /bin/bash into it to debug?
         intervention_goes_here
        """

        self.assertReMatchLines(expected, output)

