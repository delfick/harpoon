"""
This is where the mainline sits and is responsible for setting up the logging,
the argument parsing and for starting up Harpoon.
"""

from __future__ import print_function

from harpoon.errors import BadOption, BadDockerConnection
from harpoon.overview import Overview

from rainbow_logging_handler import RainbowLoggingHandler
from input_algorithms.spec_base import NotSpecified
from docker.client import Client as DockerClient
from delfick_error import DelfickError
import requests
import argparse
import logging
import docker
import ssl
import sys
import os

log = logging.getLogger("harpoon.executor")

def setup_logging(verbose=False, silent=False, debug=False):
    log = logging.getLogger("")
    handler = RainbowLoggingHandler(sys.stderr)
    handler._column_color['%(asctime)s'] = ('cyan', None, False)
    handler._column_color['%(levelname)-7s'] = ('green', None, False)
    handler._column_color['%(message)s'][logging.INFO] = ('blue', None, False)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)-15s %(message)s"))
    log.addHandler(handler)
    log.setLevel([logging.INFO, logging.DEBUG][verbose or debug])
    if silent:
        log.setLevel(logging.ERROR)

    logging.getLogger("requests").setLevel([logging.CRITICAL, logging.ERROR][verbose or debug])
    return handler

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
        if default_task is not NotSpecified and args.harpoon_chosen_task != default_task:
            raise BadOption("Please don't specify task as a positional argument and as a --task option", positional=default_task, kwarg=args.task)
        if default_image is not NotSpecified and args.harpoon_chosen_image != default_image:
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

        logging.add_argument("--debug"
            , help = "Debug logs"
            , dest = "harpoon_debug"
            , action = "store_true"
            )

        opts = {}
        if os.path.exists("./harpoon.yml"):
            opts["default"] = "./harpoon.yml"
            opts["required"] = False
        else:
            opts["required"] = True

        if "HARPOON_CONFIG" in os.environ:
            opts["default"] = os.environ["HARPOON_CONFIG"]
            del opts["required"]
        parser.add_argument("--harpoon-config"
            , help = "The config file specifying what harpoon should care about"
            , type = argparse.FileType("r")
            , **opts
            )

        extra = {"default": "list_tasks"}
        if default_task is not NotSpecified:
            extra["default"] = default_task
        parser.add_argument("--task"
            , help = "The task to run"
            , dest = "harpoon_chosen_task"
            , **extra
            )

        parser.add_argument("--non-interactive"
            , help = "Make this non interactive"
            , dest = "harpoon_interactive"
            , action = "store_false"
            )

        extra = {"default": ""}
        if default_image is not NotSpecified:
            extra["default"] = default_image
        parser.add_argument("--image"
            , help = "Specify a particular image"
            , dest = "harpoon_chosen_image"
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
            , dest = "harpoon_silent_build"
            , action = "store_true"
            )

        parser.add_argument("--keep-replaced"
            , help = "Don't delete images that have their tag stolen by a new image"
            , dest = "harpoon_keep_replaced"
            , action = "store_true"
            )

        parser.add_argument("--no-intervention"
            , help = "Don't ask to intervene broken builds"
            , dest = "harpoon_no_intervention"
            , action = "store_true"
            )

        parser.add_argument("--intervene-afterwards"
            , help = "Create an intervention container once this container exits"
            , dest = "harpoon_intervene_afterwards"
            , action = "store_true"
            )

        parser.add_argument("--no-cleanup"
            , help = "Don't automatically cleanup after a run"
            , dest = "harpoon_no_cleanup"
            , action = "store_true"
            )

        parser.add_argument("--env"
            , help = "Environment option to start the container with"
            , dest = "extra_env"
            , action = "append"
            )

        parser.add_argument("--port"
            , help = "Specify a port to publish in the running container you make"
            , dest = "extra_ports"
            , action = "append"
            )

        parser.add_argument("--flat"
            , help = "Used with the show command"
            , dest = "harpoon_flat"
            , action = "store_true"
            )

        parser.add_argument("--ignore-missing"
            , help = "Used by the pull commands to ignore if an image doesn't exist"
            , dest = "harpoon_ignore_missing"
            , action = "store_true"
            )

        return parser

    def interpret_args(self, argv, no_docker=False):
        """Parse argv, do some transformation and return cli_args suitable for Overview"""
        args, extra = CliParser().parse_args(argv)

        cli_args = {"harpoon": {}}
        for key, val in sorted(vars(args).items()):
            if key.startswith("harpoon_"):
                cli_args["harpoon"][key[8:]] = val
            else:
                cli_args[key] = val
        cli_args["harpoon"]["extra"] = extra

        if not no_docker:
            cli_args["harpoon"]["docker_context"] = docker_context()
        cli_args["harpoon"]["docker_context_maker"] = docker_context

        for key in ('bash', 'command'):
            if cli_args[key] is None:
                cli_args[key] = NotSpecified

        return args, cli_args

def docker_context():
    """Make a docker context"""
    host = os.environ.get('DOCKER_HOST')
    cert_path = os.environ.get('DOCKER_CERT_PATH')
    tls_verify = os.environ.get('DOCKER_TLS_VERIFY')

    if cert_path == '':
        cert_path = os.path.join(os.environ.get('HOME', ''), '.docker')

    options = {"timeout": 60, "version": 'auto'}
    if host:
        options['base_url'] = (host.replace('tcp://', 'https://') if tls_verify else host)

    if tls_verify and cert_path:
        options['tls'] = docker.tls.TLSConfig(
              verify = True
            , ca_cert = os.path.join(cert_path, 'ca.pem')
            , client_cert = (os.path.join(cert_path, 'cert.pem'), os.path.join(cert_path, 'key.pem'))
            , ssl_version = ssl.PROTOCOL_TLSv1
            , assert_hostname = False
            )

    client = DockerClient(**options)
    try:
        info = client.info()
        log.info("Connected to docker daemon\tdriver=%s\tkernel=%s", info["Driver"], info["KernelVersion"])
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
        raise BadDockerConnection(base_url=options.get('base_url'), error=error)
    return client

def main(argv=None):
    try:
        args, cli_args = CliParser().interpret_args(argv)
        handler = setup_logging(verbose=args.verbose, silent=args.silent, debug=args.harpoon_debug)
        Overview(configuration_file=args.harpoon_config.name, logging_handler=handler).start(cli_args)
    except DelfickError as error:
        print("")
        print("!" * 80)
        print("Something went wrong! -- {0}".format(error.__class__.__name__))
        print("\t{0}".format(error))
        if CliParser().parse_args(argv)[0].harpoon_debug:
            raise
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass

