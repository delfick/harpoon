"""
The functionality itself for each task.

Each task is specified with the ``a_task`` decorator and indicates whether it's
necessary to provide the task with the object containing all the images and/or
one specific image object.
"""
from harpoon.container_manager import make_server, Manager, wait_for_server
from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.errors import BadOption, HarpoonError
from harpoon.ship.context import ContextBuilder
from harpoon.ship.builder import Builder
from harpoon.ship.syncer import Syncer

from docker.errors import APIError as DockerAPIError
from delfick_project.norms import sb, Meta
from urllib.parse import urlparse
from functools import partial
from textwrap import dedent
from itertools import chain
import docker.errors
import itertools
import threading
import requests
import logging
import signal
import socket
import shutil
import errno
import os
import re

log = logging.getLogger("harpoon.actions")

info = {"is_default": True}
default_actions = []
available_actions = {}


class an_action(object):
    """Records a task in the ``available_actions`` dictionary"""

    def __init__(self, needs_image=False):
        self.needs_image = needs_image

    def __call__(self, func):
        available_actions[func.__name__] = func
        func.needs_image = self.needs_image
        if info["is_default"]:
            default_actions.append(func.__name__)
        return func


@an_action(needs_image=True)
def push(collector, image, **kwargs):
    """Push an image"""
    if not image.image_index:
        raise BadOption(
            "The chosen image does not have a image_index configuration", wanted=image.name
        )
    tag = kwargs["artifact"]
    if tag is sb.NotSpecified:
        tag = collector.configuration["harpoon"].tag
    if tag is not sb.NotSpecified:
        image.tag = tag
    Builder().make_image(image, collector.configuration["images"], pushing=True)
    Syncer().push(image)


@an_action()
def push_all(collector, **kwargs):
    """Push all the images"""
    configuration = collector.configuration
    configuration["harpoon"].do_push = True
    configuration["harpoon"].only_pushable = True
    make_all(collector, **kwargs)


@an_action()
def pull_arbitrary(collector, image, **kwargs):
    """Pull an arbitrary image"""
    image_index_of = lambda image: urlparse("https://{0}".format(image)).netloc

    if image.startswith("file://"):
        parsed = urlparse(image)
        filename = parsed.netloc + parsed.path
        if not os.path.exists(filename):
            raise HarpoonError("Provided file doesn't exist!", wanted=image)
        with open(filename) as fle:
            image_indexes = [(line.strip(), image_index_of(line.strip())) for line in fle]
    else:
        image_indexes = [(image, image_index_of(image))]

    authentication = collector.configuration.get("authentication", sb.NotSpecified)
    for index, (image, image_index) in enumerate(image_indexes):
        tag = sb.NotSpecified
        if ":" in image:
            image, tag = image.split(":", 1)

        image = {
            "image_name": image,
            "tag": tag,
            "harpoon": collector.configuration["harpoon"],
            "commands": ["FROM scratch"],
            "image_index": image_index,
            "assume_role": sb.NotSpecified,
            "authentication": authentication,
        }
        meta = Meta(collector.configuration, []).at("images").at("__arbitrary_{0}__".format(index))
        image = HarpoonSpec().image_spec.normalise(meta, image)
        Syncer().pull(image)


@an_action(needs_image=True)
def pull(collector, image, **kwargs):
    """Pull an image"""
    if not image.image_index:
        raise BadOption(
            "The chosen image does not have a image_index configuration", wanted=image.name
        )
    tag = kwargs["artifact"]
    if tag is sb.NotSpecified:
        collector.configuration["harpoon"].tag
    if tag is not sb.NotSpecified:
        image.tag = tag
        log.info("Pulling tag: %s", tag)
    Syncer().pull(image, ignore_missing=image.harpoon.ignore_missing)


@an_action(needs_image=True)
def pull_dependencies(collector, image, **kwargs):
    """Pull an image's dependent images"""
    for dep in image.commands.dependent_images:
        kwargs["image"] = dep
        pull_arbitrary(collector, **kwargs)


@an_action(needs_image=True)
def pull_parent(collector, image, **kwargs):
    """DEPRECATED - use pull_dependencies instead"""
    log.warning("DEPRECATED - use pull_dependencies instead")
    pull_dependencies(collector, image, **kwargs)


@an_action()
def pull_all(collector, image, **kwargs):
    """Pull all the images"""
    images = collector.configuration["images"]

    for layer in Builder().layered(images, only_pushable=True):
        for image_name, image in layer:
            log.info("Pulling %s", image_name)
            pull(collector, image, **kwargs)


@an_action()
def pull_all_external(collector, **kwargs):
    """Pull all the external dependencies of all the images"""
    deps = set()

    images = collector.configuration["images"]
    for layer in Builder().layered(images):
        for image_name, image in layer:
            for dep in image.commands.external_dependencies:
                deps.add(dep)

    for dep in sorted(deps):
        kwargs["image"] = dep
        pull_arbitrary(collector, **kwargs)


@an_action()
def pull_parents(collector, **kwargs):
    """DEPRECATED - use pull_all_external instead"""
    log.warning("DEPRECATED - use pull_all_external instead")
    pull_all_external(collector, **kwargs)


@an_action(needs_image=True)
def make(collector, image, **kwargs):
    """Just create an image"""
    tag = kwargs.get("artifact", sb.NotSpecified)
    if tag is sb.NotSpecified:
        tag = collector.configuration["harpoon"].tag

    if tag is not sb.NotSpecified:
        image.tag = tag

    Builder().make_image(image, collector.configuration["images"])
    print("Created image {0}".format(image.image_name))


@an_action()
def make_all(collector, **kwargs):
    """Creates all the images in layered order"""
    configuration = collector.configuration
    push = configuration["harpoon"].do_push
    only_pushable = configuration["harpoon"].only_pushable
    if push:
        only_pushable = True

    tag = kwargs.get("artifact", sb.NotSpecified)
    if tag is sb.NotSpecified:
        tag = configuration["harpoon"].tag

    images = configuration["images"]
    for layer in Builder().layered(images, only_pushable=only_pushable):
        for _, image in layer:
            if tag is not sb.NotSpecified:
                image.tag = tag
            Builder().make_image(image, images, ignore_deps=True, ignore_parent=True)
            print("Created image {0}".format(image.image_name))
            if push and image.image_index:
                Syncer().push(image)


@an_action()
def make_pushable(collector, **kwargs):
    """Make only the pushable images and their dependencies"""
    configuration = collector.configuration
    configuration["harpoon"].do_push = True
    configuration["harpoon"].only_pushable = True
    make_all(collector, **kwargs)


@an_action(needs_image=True)
def run(collector, image, **kwargs):
    """Run specified task in this image"""
    image.build_and_run(collector.configuration["images"])


@an_action()
def list_tasks(collector, tasks, **kwargs):
    """List the available_tasks"""
    print("Available tasks to choose from are:")
    print("Use the --task option to choose one")
    print("")
    keygetter = lambda item: item[1].label
    tasks = sorted(tasks.items(), key=keygetter)
    for label, items in itertools.groupby(tasks, keygetter):
        print("--- {0}".format(label))
        print("----{0}".format("-" * len(label)))
        sorted_tasks = sorted(list(items), key=lambda item: len(item[0]))
        max_length = max(len(name) for name, _ in sorted_tasks)
        for key, task in sorted_tasks:
            desc = dedent(task.description or "").strip().split("\n")[0]
            print("\t{0}{1} :-: {2}".format(" " * (max_length - len(key)), key, desc))
        print("")


@an_action()
def delete_untagged(collector, **kwargs):
    """Find the untagged images and remove them"""
    configuration = collector.configuration
    docker_api = configuration["harpoon"].docker_api
    images = docker_api.images()
    found = False
    for image in images:
        if image["RepoTags"] == ["<none>:<none>"]:
            found = True
            image_id = image["Id"]
            log.info("Deleting untagged image\thash=%s", image_id)
            try:
                docker_api.remove_image(image["Id"])
            except DockerAPIError as error:
                log.error("Failed to delete image\thash=%s\terror=%s", image_id, error)

    if not found:
        log.info("Didn't find any untagged images to delete!")


@an_action()
def show(collector, **kwargs):
    """Show what images we have"""
    configuration = collector.configuration
    flat = configuration.get("harpoon.flat", False)
    only_pushable = configuration.get("harpoon.only_pushable", False)

    for index, layer in enumerate(
        Builder().layered(configuration["images"], only_pushable=only_pushable)
    ):
        if flat:
            for _, image in layer:
                print(image.image_name)
        else:
            print("Layer {0}".format(index))
            for _, image in layer:
                print("    {0}".format(image.display_line()))
            print("")


@an_action()
def show_pushable(collector, **kwargs):
    """Show what images we have"""
    collector.configuration["harpoon"].only_pushable = True
    show(collector, **kwargs)


@an_action(needs_image=True)
def print_dockerfile(collector, image, **kwargs):
    """Print a dockerfile for the specified image"""
    print("\n".join(image.docker_file.docker_lines))


@an_action(needs_image=True)
def get_docker_context(collector, image, **kwargs):
    """Output the context that would be sent to docker if we made this image"""
    with image.make_context() as context:
        context.close()
        shutil.copyfile(context.name, os.environ.get("FILENAME", f"./context_{image.name}.tar"))


@an_action()
def print_all_dockerfiles(collector, **kwargs):
    """Print all the dockerfiles"""
    for name, image in collector.configuration["images"].items():
        print("{0}".format(name))
        print("-" * len(name))
        kwargs["image"] = image
        print_dockerfile(collector, **kwargs)


@an_action()
def read_login(collector, image, **kwargs):
    """Login to a docker registry with read permissions"""
    docker_api = collector.configuration["harpoon"].docker_api
    collector.configuration["authentication"].login(
        docker_api, image, is_pushing=False, global_docker=True
    )


@an_action()
def write_login(collector, image, **kwargs):
    """Login to a docker registry with write permissions"""
    docker_api = collector.configuration["harpoon"].docker_api
    collector.configuration["authentication"].login(
        docker_api, image, is_pushing=True, global_docker=True
    )


@an_action(needs_image=True)
def untag(collector, image, artifact, **kwargs):
    """Tag an image!"""
    if artifact in (None, "", sb.NotSpecified):
        artifact = collector.configuration["harpoon"].tag

    if artifact is sb.NotSpecified:
        raise BadOption("Please specify a tag using the artifact or tag options")

    image.tag = artifact
    image_name = image.image_name_with_tag

    log.info("Removing image\timage={0}".format(image_name))
    try:
        image.harpoon.docker_api.remove_image(image_name)
    except docker.errors.ImageNotFound:
        log.warning("No image was found to remove")


@an_action(needs_image=True)
def tag(collector, image, artifact, **kwargs):
    """Tag an image!"""
    if artifact in (None, "", sb.NotSpecified):
        raise BadOption("Please specify a tag using the artifact option")

    if image.image_index in (None, "", sb.NotSpecified):
        raise BadOption("Please specify an image with an image_index option")

    tag = image.image_name
    if collector.configuration["harpoon"].tag is not sb.NotSpecified:
        tag = "{0}:{1}".format(tag, collector.configuration["harpoon"].tag)
    else:
        tag = "{0}:latest".format(tag)

    images = image.harpoon.docker_api.images()
    current_tags = chain.from_iterable(
        image_conf["RepoTags"] for image_conf in images if image_conf["RepoTags"] is not None
    )
    if tag not in current_tags:
        raise BadOption("Please build or pull the image down to your local cache before tagging it")

    for image_conf in images:
        if image_conf["RepoTags"] is not None:
            if tag in image_conf["RepoTags"]:
                image_id = image_conf["Id"]
                break

    log.info("Tagging {0} ({1}) as {2}".format(image_id, image.image_name, artifact))
    image.harpoon.docker_api.tag(image_id, repository=image.image_name, tag=artifact, force=True)

    image.tag = artifact
    Syncer().push(image)


@an_action(needs_image=True)
def retrieve(collector, image, artifact, **kwargs):
    """Retrieve a file/folder from an image"""
    if artifact in (None, "", sb.NotSpecified):
        raise BadOption("Please specify what to retrieve using the artifact option")

    if collector.configuration["harpoon"].tag is not sb.NotSpecified:
        image.tag = collector.configuration["harpoon"].tag

    # make sure the image is built
    if os.environ.get("NO_BUILD") is None:
        Builder().make_image(image, collector.configuration["images"])

    content = {
        "conf": image,
        "docker_api": collector.configuration["harpoon"].docker_api,
        "images": collector.configuration["images"],
        "image": image.image_name_with_tag,
        "path": artifact,
    }

    # Get us our gold!
    with ContextBuilder().the_context(content) as fle:
        shutil.copyfile(fle.name, os.environ.get("FILENAME", "./retrieved.tar.gz"))


@an_action()
def container_manager(collector, image, **kwargs):
    """
    Start a web server that you can request containers from.

    Usage is like::

        harpoon container_manager pathtofile

    Or::

        harpoon container_manager pathtofile:port

    Or::

        harpoon container_manager :port

    If pathtofile is specified then we will fork the process, start the web
    server in the forked process, write the port of the web server and pid on
    separate lines to the file specified by pathtofile and quit

    If port is not specified, then we will bind to an available port, otherwise
    we bind the web server to the specified port.

    If no argument is specified, it's the same as saying::

        harpoon container_manager :4545
    """
    if image in (None, "", sb.NotSpecified):
        image = ":4545"

    m = re.match(r"([^:]+)?(?::(\d+))?", image)

    if not m:
        raise HarpoonError("First argument to container_manager was invalid")

    groups = m.groups()
    filename = groups[0]

    port = int(groups[1] or 0)
    if not port:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", 0))
            port = s.getsockname()[1]

    if filename:
        pid = os.fork()
        if pid != 0:
            with open(filename, "w") as fle:
                fle.write(str(port))
                fle.write("\n")
                fle.write(str(pid))
                fle.write("\n")

            wait_for_server(port)
            return

    image_puller = partial(pull_arbitrary, collector)
    manager = Manager(
        collector.configuration["harpoon"],
        collector.configuration["images"],
        image_puller=image_puller,
    )

    def shutdown(signum, frame):
        if not manager.shutting_down:
            url = "http://127.0.0.1:{0}/shutdown".format(port)
            thread = threading.Thread(target=requests.get, args=(url,))
            thread.daemon = True
            thread.start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start our server
    try:
        server = make_server(manager, ("0.0.0.0", port))
        log.info("Serving container manager on 0.0.0.0:{0}".format(port))
        server.serve_forever()
    except OSError as error:
        if error.errno == errno.EADDRINUSE:
            raise HarpoonError(
                "Container manager couldn't start because port was already in use", wanted=port
            )
        raise


# Make it so future use of @an_action doesn't result in more default tasks
info["is_default"] = False
