.. _bh_s2_recap_two:

Recap Two
=========

So now we should have something like the following:

``config.yml``

    .. code-block:: yaml

        ---

        tag: local/lolz

        commands:
            - FROM gliderlabs/alpine:3.1
            - RUN apk-install figlet --update-cache --repository http://dl-3.alpinelinux.org/alpine/edge/main/
            - CMD figlet lolz

``setup.py``

    .. code-block:: python

        from setuptools import setup, find_packages

        setup(
            name = "my-harpoon"
            , version = 0.1
            , packages = ['harpoon'] + ['harpoon.%s' % pkg for pkg in find_packages('harpoon')]

            , install_requires =
              [ "delfick_app==0.6.7"
              , "docker-py==1.2.2"
              , "dockerpty==0.3.4"
              , "pyYaml==3.11"
              , "requests[security]"
              , "input_algorithms==0.4.4.6"
              , "option_merge==0.9.8.2"
              ]

            , entry_points =
              { 'console_scripts' :
                [ 'harpoon = harpoon.executor:main'
                ]
              }
            )

``harpoon/``

    ``__init__.py``

    ``errors.py``

        .. code-block:: python

            from delfick_error import DelfickError

            class BadImage(DelfickError):
                desc = "Something bad about the image"
            class BadContainer(DelfickError):
                desc = "Something bad about the container"

    ``actions.py``

        .. code-block:: python

            available_actions = {}

            def an_action(func):
                available_actions[func.__name__] = func
                return func

            @an_action
            def list_tasks(collector, cli_args):
                """Tasks themselves don't get introduced till section3, so let's just list the actions"""
                print('\n'.join("{0}: {1}".format(name, func.__doc__) for name, func in available_actions.items()))

            @an_action
            def build_and_run(collector, cli_args):
                """Build and run an image"""
                image = collector.configuration["image"]
                harpoon = cli_args["harpoon"]

                image.build(harpoon)
                image.run(harpoon)

    ``collector.py``

        .. code-block:: python

            from harpoon.option_spec.image_objs import image_spec
            from harpoon.actions import available_actions

            from option_merge.collector import Collector
            from option_merge import MergedOptions
            from input_algorithms.meta import Meta
            import yaml

            class Collector(Collector):
                def read_file(self, location):
                    return yaml.load(open(location))

                def start_configuration(self):
                    return MergedOptions()

                def add_configuration(self, configuration, collect_another_source, done, result, src):
                    configuration.update(result)

                def extra_prepare(self, configuration, cli_args):
                    configuration.update(
                          { "harpoon": cli_args["harpoon"]
                          , "cli_args": cli_args
                          }
                        )

                def extra_configuration_collection(self, configuration):
                    meta = Meta(configuration, [])
                    configuration["image"] = image_spec.normalise(meta, configuration)

                def start(self):
                    chosen_task = self.configuration["harpoon"]["task"]
                    available_actions[chosen_task](self, self.configuration["cli_args"])

    ``executor.py``

        .. code-block:: python

            from harpoon.collector import Collector

            from delfick_app import App
            import argparse
            import logging
            import docker

            class Harpoon(App):
                cli_categories = ['harpoon']
                cli_positional_replacements = [('--task', 'list_tasks')]

                def execute(self, args, extra_args, cli_args, logging_handler):
                    cli_args['harpoon']['make_client'] = make_client

                    collector = Collector()
                    collector.prepare(args.config.name, cli_args)
                    collector.start()

                def specify_other_args(self, parser, defaults):
                    parser.add_argument("--config"
                        , help = "Location of the configuration"
                        , type = argparse.FileType('r')
                        , default = "./config.yml"
                        )

                    parser.add_argument('--task'
                        , help = 'The task to run'
                        , dest = 'harpoon_task'
                        , **defaults['--task']
                        )

                def setup_other_logging(self, args, verbose=False, silent=False, debug=False):
                    logging.getLogger("requests").setLevel([logging.CRITICAL, logging.ERROR][verbose or debug])

            def make_client():
                """Make a docker context"""
                return docker.Client(**docker.utils.kwargs_from_env(assert_hostname=False))

            main = Harpoon.main
            if __name__ == "__main__":
                main()

    ``option_spec/``

        ``__init__.py``

        ``image_objs.py``

            .. code-block:: python

                from harpoon.errors import BadImage, BadContainer

                from input_algorithms import spec_base as sb
                import dockerpty
                import tempfile
                import logging
                import docker
                import yaml
                import ssl
                import sys
                import os

                log = logging.getLogger("harpoon.option_spec.image_objs")

                class Image(object):
                    def __init__(self, tag, commands):
                        self.tag = tag
                        self.commands = commands

                    def dockerfile(self):
                        dockerfile = tempfile.NamedTemporaryFile(delete=True)
                        dockerfile.write("\n".join(self.commands))
                        dockerfile.flush()
                        dockerfile.seek(0)
                        return dockerfile

                    def build(self, harpoon):
                        client = harpoon["make_client"]()
                        log.info("Building an image: %s", self.tag)

                        try:
                            for line in client.build(fileobj=self.dockerfile(), rm=True, tag=self.tag, pull=False):
                                print(line)
                        except docker.errors.APIError as error:
                            raise BadImage("Failed to build the image", tag=self.tag, error=error)

                    def run(self, harpoon):
                        client = harpoon["make_client"]()
                        log.info("Making a container from an image (%s)", self.tag)
                        try:
                            container = client.create_container(image=self.tag)
                        except docker.errors.APIError as error:
                            raise BadImage("Failed to create the container", image=self.tag, error=error)

                        log.info("Starting a container: %s", container["Id"])
                        try:
                            dockerpty.start(harpoon['make_client'](), container)
                        except docker.errors.APIError as error:
                            raise BadContainer("Failed to start the container", container=container["Id"], image=self.tag, error=error)

                        log.info("Cleaning up a container: %s", container["Id"])
                        try:
                            client.remove_container(container)
                        except docker.errors.APIError as error:
                            log.error("Failed to remove the container :(\tcontainer=%s\terror=%s", container["Id"], error)

                image_spec = sb.create_spec(Image
                    , tag = sb.string_spec()
                    , commands = sb.listof(sb.string_spec())
                    )

This may look a bit over the top at the moment, but it gives us a good
foundation for adding many features. We only have 126 lines of python over 5
files here if we exclude blank lines. Harpoon itself is nearly 2500 lines of python
over 20 files!
