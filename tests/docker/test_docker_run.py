#coding: spec

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.ship.runner import Runner
from harpoon.errors import FailedImage

from tests.helpers import HarpoonCase

from option_merge.converter import Converter
from option_merge import MergedOptions
from input_algorithms.meta import Meta
import codecs
import nose
import mock
import six
import os

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
        if six.PY3:
            raise nose.SkipTest()

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
            self.assertEqual(str(error.kwargs["msg"]), "The command [/bin/sh -c exit 1] returned a non-zero code: 1")
            self.assertEqual(error.kwargs["image"], "awesome_image")

        self.assertEqual(called, ["commit_and_run"])

        with codecs.open(fake_sys_stdout.name, errors='ignore') as fle:
            output = fle.read().strip().decode('utf-8', 'ignore')

        output = '\n'.join([line for line in output.split('\n') if "lxc-start" not in line])

        expected = """
         Step 0 : FROM busybox:buildroot-2014.02
          ---> 8c2e06607696
         Step 1 : RUN exit 1
          ---> Running in .+
         !!!!
         It would appear building the image failed
         Do you want to run /bin/bash where the build to help debug why it failed?
         intervention_goes_here
        """

        self.assertReMatchLines(expected, output)

