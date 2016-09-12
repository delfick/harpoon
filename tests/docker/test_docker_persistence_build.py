#coding: spec

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.ship.builder import Builder
from harpoon.ship.runner import Runner
from harpoon.errors import BadImage

from tests.helpers import HarpoonCase

from option_merge.converter import Converter
from option_merge import MergedOptions
from input_algorithms.meta import Meta
from itertools import chain
import docker.errors
import logging
import os

mtime = 1431170923

log = logging.getLogger("tests.docker.test_docker_persistence_build")

describe HarpoonCase, "Persistence builds":
    def make_image(self, options, harpoon_options=None):
        config_root = self.make_temp_dir()
        if harpoon_options is None:
            harpoon_options = {}
        harpoon_options["docker_context"] = self.docker_client
        harpoon_options["no_intervention"] = True
        harpoon_options["docker_context_maker"] = self.new_docker_client

        harpoon = HarpoonSpec().harpoon_spec.normalise(Meta({}, []), harpoon_options)
        if "harpoon" not in options:
            options["harpoon"] = harpoon

        everything = MergedOptions.using({"harpoon": harpoon, "mtime": mtime, "config_root": config_root})
        everything.update({"images": {"awesome_image": options}})

        def make_options():
            base = everything.wrapped()
            base.update(options)
            base["configuration"] = everything
            return base

        meta = Meta(everything, []).at("images").at("awesome_image")
        harpoon_converter = Converter(convert=lambda *args: harpoon, convert_path=["harpoon"])
        image_converter = Converter(
              convert=lambda *args: HarpoonSpec().image_spec.normalise(meta, make_options())
            , convert_path=["images", "awesome_image"]
            )

        everything.add_converter(harpoon_converter)
        everything.add_converter(image_converter)
        everything.converters.activate()

        return everything[["images", "awesome_image"]]

    it "works":
        ########################
        ###   SETUP AND SANITY
        ########################

        conf = self.make_image(
            { "context": False
            , "commands":
              [ "FROM {0}".format(os.environ["BASE_IMAGE"])
              , "RUN echo 'a_line' > /tmp/lines"
              ]
            , "persistence":
              { "action": "cat /tmp/lines > /tmp/lines2; echo 'another_line' >> /tmp/lines2; mv /tmp/lines2 /tmp/lines"
              , "folders": "/tmp"
              , "shell": "sh"
              }
            }
        )

        # We test later on:
        #  * that we don't create new volumes
        #  * only create two new images
        #  * Don't leave behind running containers
        originals = {}

        set_tags_to_ids = lambda: originals.__setitem__("tags_to_ids"
            , list(chain.from_iterable(
                [(rt, ident) for rt in rts] for rts, ident in [
                  (i['RepoTags'], i['Id']) for i in
                    conf.harpoon.docker_context.images()
                ]
            ))
        )

        set_original_tags = lambda: originals.__setitem__("tags"
            , [t2id[0] for t2id in originals["tags_to_ids"]]
            )
        set_original_images = lambda: originals.__setitem__("images"
            , [i['Id'] for i in conf.harpoon.docker_context.images()]
            )
        set_original_volumes = lambda: originals.__setitem__("volumes"
            , conf.harpoon.docker_context.volumes()['Volumes'] or []
            )
        set_original_containers = lambda: originals.__setitem__("containers"
            , [c['Id'] for c in conf.harpoon.docker_context.containers(all=True)]
            )

        setters = [set_tags_to_ids, set_original_tags, set_original_images, set_original_volumes, set_original_containers]
        set_originals = lambda: [s() for s in setters]
        set_originals()

        tests = []
        collected = {"images": []}
        def test(func):
            tests.append(func)
            return func

        ########################
        ###   CHECKERS
        ########################

        def assert_same_volumes():
            self.assertEqual(originals["volumes"], conf.harpoon.docker_context.volumes()["Volumes"] or [])

        def assert_same_containers():
            self.assertEqual(originals["containers"], [i['Id'] for i in conf.harpoon.docker_context.containers(all=True)])

        def assert_extra_tags(*extra):
            new_tags = list(chain.from_iterable(i['RepoTags'] for i in conf.harpoon.docker_context.images()))
            self.assertEqual(sorted(new_tags), sorted(originals["tags"] + list(extra)))

        def assert_only_extra_tags(*extra):
            assert_same_volumes()
            assert_same_containers()
            assert_extra_tags(*extra)

        ########################
        ###   CLEANUP
        ########################

        for container in originals["containers"]:
            print("Removing container: {0}".format(container))
            try:
                conf.harpoon.docker_context.kill(container, 9)
            except:
                pass
            conf.harpoon.docker_context.remove_container(container)

        for tag, ident in dict(originals["tags_to_ids"]).items():
            if tag == "<none>:<none>":
                print("Removing <none>:<none> image: {0}".format(ident))
                conf.harpoon.docker_context.remove_image(ident)

        for unwanted in (conf.image_name, "{0}:latest".format(conf.image_name), "{0}-tester:latest".format(conf.image_name)):
            if unwanted in originals["tags"]:
                print("Removing unwanted image: {0}".format(unwanted))
                conf.harpoon.docker_context.remove_image(unwanted)

        set_originals()

        ########################
        ###   TEST DEFINITIONS
        ########################

        @test
        it "just runs the docker commands and action the first time along with the tester image":
            cached = Builder().make_image(conf, {conf.name: conf})
            collected["images"].append(conf.image_name)
            assert_only_extra_tags("{0}:latest".format(conf.image_name), "{0}-tester:latest".format(conf.image_name))

            last_id = None
            commands = []
            for line in conf.harpoon.docker_context.history(conf.image_name):
                if os.environ["BASE_IMAGE"] in (line["Tags"] or []):
                    break

                last_id = line['Id']
                commands.append(line["CreatedBy"])

            self.assertEqual(commands
                , [ '/bin/sh -c #(nop)  CMD ["/bin/sh" "-c" "sh"]'
                  , '/bin/sh -c sh -c \'cat /tmp/lines > /tmp/lines2; echo \'"\'"\'another_line\'"\'"\' >> /tmp/lines2; mv /tmp/lines2 /tmp/lines\''
                  , "/bin/sh -c echo 'a_line' > /tmp/lines"
                  ]
                )

            found = False
            tester_commands = []
            for line in conf.harpoon.docker_context.history("{0}-tester:latest".format(conf.image_name)):
                if line['Id'] == last_id:
                    found = True
                    break
                tester_commands.append(line["CreatedBy"])

            assert found, "Tester wasn't based on the first image!"
            self.assertEqual(tester_commands
                , [ '/bin/sh -c echo sh'
                  , '/bin/sh -c echo /tmp'
                  , '/bin/sh -c echo \'cat /tmp/lines > /tmp/lines2; echo \'"\'"\'another_line\'"\'"\' >> /tmp/lines2; mv /tmp/lines2 /tmp/lines\''
                  ]
                )

        @test
        it "can be run after the first time":
            conf.command = "/bin/sh -c 'cat /tmp/lines'"
            fake_sys_stdout = self.make_temp_file()
            fake_sys_stderr = self.make_temp_file()
            conf.harpoon.tty_stdout = fake_sys_stdout
            conf.harpoon.tty_stderr = fake_sys_stderr
            try:
                Runner().run_container(conf, {conf.name: conf})
            except (docker.errors.APIError, BadImage) as error:
                log.exception(error)

            with open(fake_sys_stdout.name) as fle:
                output = fle.read().strip().replace("\r", "")

            with open(fake_sys_stderr.name) as fle:
                self.assertEqual(fle.read().strip(), '')

            self.assertEqual(output, "a_line\nanother_line")
            assert_only_extra_tags("{0}:latest".format(conf.image_name), "{0}-tester:latest".format(conf.image_name))

        @test
        it "says image is cached if nothing has changed":
            cached = Builder().make_image(conf, {conf.name: conf})
            assert cached, "The build should have been cached!@"

            # Rerun our second test, it should be the same
            test_can_be_run_after_the_first_time(self)

        @test
        it "takes persists the specified folders between builds":
            conf.commands.commands[1].command = "echo    'a_line' > /tmp/lines"
            del conf._docker_file
            cached = Builder().make_image(conf, {conf.name: conf})
            assert not cached, "But we changed the command!"

            commands = []
            for line in conf.harpoon.docker_context.history(conf.image_name):
                if os.environ["BASE_IMAGE"] in (line["Tags"] or []):
                    break

                last_id = line['Id']
                commands.append(line["CreatedBy"])

            self.assertEqual(commands
                , [ '/bin/sh -c #(nop)  CMD ["/bin/sh" "-c" "sh"]'
                  , "/bin/sh -c echo /tmp && rm -rf /tmp && mkdir -p $(dirname /tmp) && mv /awesome_image/_tmp /tmp && cat /tmp/lines > /tmp/lines2; echo 'another_line' >> /tmp/lines2; mv /tmp/lines2 /tmp/lines"
                  , '/bin/sh -c #(nop)  CMD ["/bin/sh" "-c" "echo /tmp && rm -rf /tmp && mkdir -p $(dirname /tmp) && mv /awesome_image/_tmp /tmp && cat /tmp/lines > /tmp/lines2; echo \'another_line\' >> /tmp/lines2; mv /tmp/lines2 /tmp/lines"]'
                  , "/bin/sh -c echo    'a_line' > /tmp/lines"
                  ]
                )

            conf.command = "/bin/sh -c 'cat /tmp/lines'"
            fake_sys_stdout = self.make_temp_file()
            fake_sys_stderr = self.make_temp_file()
            conf.harpoon.tty_stdout = fake_sys_stdout
            conf.harpoon.tty_stderr = fake_sys_stderr
            try:
                Runner().run_container(conf, {conf.name: conf})
            except (docker.errors.APIError, BadImage) as error:
                log.exception(error)

            with open(fake_sys_stdout.name) as fle:
                output = fle.read().strip().replace('\r', '')

            with open(fake_sys_stderr.name) as fle:
                self.assertEqual(fle.read().strip(), '')

            self.assertEqual(output, "a_line\nanother_line\nanother_line")
            assert_only_extra_tags("{0}:latest".format(conf.image_name), "{0}-tester:latest".format(conf.image_name))

        ########################
        ###   TEST RUNNING
        ########################

        try:
            for test in tests:
                print("Running test: {0}".format(test.__name__))
                test(self)
        finally:
            for image in collected['images']:
                try:
                    log.info("Removing test image")
                    conf.harpoon.docker_context.remove_image(image)
                except Exception as error:
                    log.error("Failed to remove test image")
                    log.exception(error)

