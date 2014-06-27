from harpoon.errors import HarpoonError, BadOption
from harpoon.overview import Harpoon

from rainbow_logging_handler import RainbowLoggingHandler
from docker.client import Client as DockerClient
import argparse
import logging
import sys
import os

log = logging.getLogger("harpoon.executor")

class NotSpecified(object):
    """Tell the difference between None and Empty"""

def setup_logging(verbose=False, silent=False):
    log = logging.getLogger("")
    handler = RainbowLoggingHandler(sys.stderr)
    handler._column_color['%(asctime)s'] = ('cyan', None, False)
    handler._column_color['%(levelname)-7s'] = ('green', None, False)
    handler._column_color['%(message)s'][logging.INFO] = ('blue', None, False)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)-15s %(message)s"))
    log.addHandler(handler)
    log.setLevel([logging.INFO, logging.DEBUG][verbose])
    if silent:
        log.setLevel(logging.ERROR)

    logging.getLogger("requests").setLevel([logging.CRITICAL, logging.ERROR][verbose])

class CliParser(object):
    """Knows what argv looks like"""
    def parse_args(self, argv=None):
        """Split the args into <args> -- <extra_args> and run <args> through our argparse.ArgumentParser"""
        if argv is None:
            argv = sys.argv[1:]

        argv = list(argv)
        args = []
        extras = None
        default_task = NotSpecified
        default_image = NotSpecified

        if argv:
            if not argv[0].startswith("-"):
                default_task = argv[0]
                argv.pop(0)

            if argv and not argv[0].startswith("-"):
                default_image = argv[0]
                argv.pop(0)

        while argv:
            nxt = argv.pop(0)
            if extras is not None:
                extras.append(nxt)
            elif nxt == "--":
                extras = []
            else:
                args.append(nxt)

        other_args = ""
        if extras:
            other_args = " ".join(extras)

        parser = self.make_parser(default_task=default_task, default_image=default_image)
        args = parser.parse_args(args)
        if default_task is not NotSpecified and args.task != default_task:
            raise BadOption("Please don't specify task as a positional argument and as a --task option", positional=default_task, kwarg=args.task)
        if default_image is not NotSpecified and args.image != default_image:
            raise BadOption("Please don't specify image as a positional argument and as a --image option", positional=default_image, kwargs=args.image)

        return args, other_args

    def make_parser(self, default_task=NotSpecified, default_image=NotSpecified):
        parser = argparse.ArgumentParser(description="Opinionated layer around docker")

        logging = parser.add_mutually_exclusive_group()
        logging.add_argument("--verbose"
            , help = "Enable debug logging"
            , action = "store_true"
            )

        logging.add_argument("--silent"
            , help = "Only log errors"
            , action = "store_true"
            )

        opts = {}
        if os.path.exists("./harpoon.yml"):
            opts["default"] = "./harpoon.yml"
        parser.add_argument("--harpoon-config"
            , help = "The config file specifying what harpoon should care about"
            , type = argparse.FileType("r")
            , required = True
            , **opts
            )

        extra = {"default": "list_tasks"}
        if default_task is not NotSpecified:
            extra["default"] = default_task
        parser.add_argument("--task"
            , help = "The task to run"
            , **extra
            )

        parser.add_argument("--non-interactive"
            , help = "Make this non interactive"
            , dest = "interactive"
            , action = "store_false"
            )

        extra = {}
        if default_image is not NotSpecified:
            extra["default"] = default_image
        parser.add_argument("--image"
            , help = "Specify a particular image"
            , **extra
            )

        command = parser.add_mutually_exclusive_group()

        command.add_argument("--command"
            , help = "Specify a command to run for tasks that need one"
            )

        command.add_argument("--bash"
            , help = "Specify a command that will be ran as /bin/bash -c '<command>'"
            )

        parser.add_argument("--silent-build"
            , help = "Make the build process quiet"
            , action = "store_true"
            )

        parser.add_argument("--keep-replaced"
            , help = "Don't delete images that have their tag stolen by a new image"
            , action = "store_true"
            )

        parser.add_argument("--no-intervention"
            , help = "Don't ask to intervene broken builds"
            , action = "store_true"
            )

        parser.add_argument("--env"
            , help = "Environment option to start the container with"
            , action = "append"
            )

        return parser

def docker_context():
    """Make a docker context"""
    base_url = None
    if "DOCKER_HOST" in os.environ:
        base_url = os.environ["DOCKER_HOST"]
    return DockerClient(base_url=base_url, timeout=5)

def main(argv=None):
    try:
        args, extra = CliParser().parse_args(argv)
        setup_logging(verbose=args.verbose, silent=args.silent)

        kwargs = vars(args)
        kwargs["extra"] = extra
        Harpoon(configuration_file=args.harpoon_config.name, docker_context=docker_context(), interactive=args.interactive, silent_build=args.silent_build).start(**kwargs)
    except HarpoonError as error:
        print ""
        print "!" * 80
        print "Something went wrong! -- {0}".format(error.__class__.__name__)
        print "\t{0}".format(error)
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass

