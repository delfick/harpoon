.. _bh_s1_recap_one:

Recap One
=========

Congratulations!! You have a bare minimum application that reads configuration,
builds an image, runs a container, complete with colourful logs and very
rudimentary error handling.

You should have something like:

.. code-block:: python

    #!/usr/bin/env python

    from delfick_error import DelfickError
    from delfick_app import App
    import dockerpty
    import argparse
    import tempfile
    import logging
    import docker
    import yaml
    import ssl
    import sys
    import os

    log = logging.getLogger("harpoon")

    class BadImage(DelfickError):
        desc = "Something bad about the image"
    class BadContainer(DelfickError):
        desc = "Something bad about the container"

    def make_client():
        """Make a docker context"""
        return docker.Client(**docker.utils.kwargs_from_env(assert_hostname=False))

    class Harpoon(App):
        def execute(self, args, extra_args, cli_args, logging_handler):
            log.info("Reading configuration from %s", args.config.name)
            config = yaml.load(args.config)
            tag = config["tag"]
            dockerfile_commands = config["commands"]

            client = make_client()

            dockerfile = tempfile.NamedTemporaryFile(delete=True)
            dockerfile.write("\n".join(dockerfile_commands))
            dockerfile.flush()
            dockerfile.seek(0)

            log.info("Building an image: %s", tag)
            try:
                for line in client.build(fileobj=dockerfile, rm=True, tag=tag, pull=False):
                    print(line)
            except docker.errors.APIError as error:
                raise BadImage("Failed to build the image", tag=tag, error=error)

            log.info("Making a container from an image (%s)", tag)
            try:
                container = client.create_container(image=tag)
            except docker.errors.APIError as error:
                raise BadImage("Failed to create the container", image=tag, error=error)

            log.info("Starting a container: %s", container["Id"])
            try:
                dockerpty.start(make_client(), container)
            except docker.errors.APIError as error:
                raise BadContainer("Failed to start the container", container=container["Id"], image=tag, error=error)

            log.info("Cleaning up a container: %s", container["Id"])
            try:
                client.remove_container(container)
            except docker.errors.APIError as error:
                log.error("Failed to remove the container :(\tcontainer=%s\terror=%s", container["Id"], error)

        def specify_other_args(self, parser, defaults):
            parser.add_argument("--config"
                , help = "Location of the configuration"
                , type = argparse.FileType('r')
                , default = "./config.yml"
                )

        def setup_other_logging(self, args, verbose=False, silent=False, debug=False):
            logging.getLogger("requests").setLevel([logging.CRITICAL, logging.ERROR][verbose or debug])

    main = Harpoon.main
    if __name__ == "__main__":
        main()

In the next section I'll make you start to break things out into several files
and folders, as well as introduce you to the last two libraries I made as part of
implementing the actual Harpoon.

By the end of the next section you should be able to have multiple images defined
in the same configuration, error handling and validation around input from the
configuration and the ability to define tasks.

