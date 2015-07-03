"""
This is where the mainline sits and is responsible for setting up the logging,
the argument parsing and for starting up Harpoon.
"""

from harpoon.errors import BadDockerConnection
from harpoon.collector import Collector

from input_algorithms.spec_base import NotSpecified
from docker.client import Client as DockerClient
from delfick_app import App
import argparse
import requests
import logging
import docker
import ssl
import os

log = logging.getLogger("harpoon.executor")

def docker_context():
    """Make a docker context"""
    host = os.environ.get('DOCKER_HOST')
    cert_path = os.environ.get('DOCKER_CERT_PATH')
    tls_verify = os.environ.get('DOCKER_TLS_VERIFY')

    if cert_path == '':
        cert_path = os.path.join(os.environ.get('HOME', ''), '.docker')

    options = {"timeout": 180, "version": 'auto'}
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

class App(App):
    cli_categories = ['harpoon']
    cli_description = "Docker client that reads yaml"
    cli_environment_defaults = {"HARPOON_CONFIG": ("--harpoon-config", './harpoon.yml')}
    cli_positional_replacements = [('--task', 'list_tasks'), ('--image', NotSpecified)]

    def execute(self, args, extra_args, cli_args, logging_handler, no_docker=False):
        collector = Collector(configuration_file=args.harpoon_config.name)

        cli_args["harpoon"]["extra"] = extra_args

        if not no_docker:
            cli_args["harpoon"]["docker_context"] = docker_context()
        cli_args["harpoon"]["docker_context_maker"] = docker_context

        for key in ('bash', 'command'):
            if cli_args[key] is None:
                cli_args[key] = NotSpecified

        if "term_colors" in collector.configuration:
            self.setup_logging_theme(logging_handler, colors=collector.configuration["term_colors"])

        collector.prepare(cli_args)
        collector.configuration["task_runner"](collector.configuration["harpoon"].chosen_task)

    def setup_other_logging(self, args, verbose=False, silent=False, debug=False):
        logging.getLogger("requests").setLevel([logging.CRITICAL, logging.ERROR][verbose or debug])

    def specify_other_args(self, parser, defaults):
        parser.add_argument("--harpoon-config"
            , help = "The config file specifying what harpoon should care about"
            , type = argparse.FileType("r")
            , **defaults["--harpoon-config"]
            )

        parser.add_argument("--dry-run"
            , help = "Should Harpoon take any real action or print out what is intends to do"
            , dest = "harpoon_dry_run"
            , action = "store_true"
            )

        parser.add_argument("--task"
            , help = "The task to run"
            , dest = "harpoon_chosen_task"
            , **defaults["--task"]
            )

        parser.add_argument("--image"
            , help = "Specify a particular image"
            , dest = "harpoon_chosen_image"
            , **defaults["--image"]
            )

        parser.add_argument("--non-interactive"
            , help = "Make this non interactive"
            , dest = "harpoon_interactive"
            , action = "store_false"
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

main = App.main
if __name__ == '__main__':
    main()
