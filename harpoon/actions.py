"""
The functionality itself for each task.

Each task is specified with the ``a_task`` decorator and indicates whether it's
necessary to provide the task with the object containing all the images and/or
one specific image object.
"""
from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.ship.builder import Builder
from harpoon.ship.syncer import Syncer
from harpoon.errors import BadOption

from docker.errors import APIError as DockerAPIError
from input_algorithms.spec_base import NotSpecified
from input_algorithms import spec_base as sb
from six.moves.urllib.parse import urlparse
from input_algorithms.meta import Meta
from textwrap import dedent
import itertools
import logging
import six

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
        raise BadOption("The chosen image does not have a image_index configuration", wanted=image.name)
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
    image_index = urlparse("https://{0}".format(image)).netloc
    image = {
          "image_name": image
        , "harpoon": collector.configuration["harpoon"]
        , "commands": ["FROM scratch"]
        , "image_index": image_index
        , "assume_role": NotSpecified
        , "authentication": collector.configuration.get("authentication", ignore_converters=True).as_dict()
        }
    image = HarpoonSpec().image_spec.normalise(Meta(collector.configuration, []).at("images").at("__arbitrary__"), image)
    Syncer().pull(image)

@an_action(needs_image=True)
def pull(collector, image, **kwargs):
    """Pull an image"""
    if not image.image_index:
        raise BadOption("The chosen image does not have a image_index configuration", wanted=image.name)
    Syncer().pull(image, ignore_missing=image.harpoon.ignore_missing)

@an_action(needs_image=True)
def pull_parent(collector, image, **kwargs):
    """Pull an image's parent image"""
    parent_image = image.commands.parent_image
    if not isinstance(parent_image, six.string_types):
        parent_image = parent_image.image_name
    pull_arbitrary(collector, parent_image, **kwargs)

@an_action()
def pull_all(collector, **kwargs):
    """Pull all the images"""
    images = collector.configuration["images"]
    for layer in Builder().layered(images, only_pushable=True):
        for image_name, image in layer:
            log.info("Pulling %s", image_name)
            Syncer().pull(image, ignore_missing=image.harpoon.ignore_missing)

@an_action(needs_image=True)
def make(collector, image, **kwargs):
    """Just create an image"""
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

    images = configuration["images"]
    for layer in Builder().layered(images, only_pushable=only_pushable):
        for _, image in layer:
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
            desc = dedent(task.description or "").strip().split('\n')[0]
            print("\t{0}{1} :-: {2}".format(" " * (max_length-len(key)), key, desc))
        print("")

@an_action()
def delete_untagged(collector, **kwargs):
    """Find the untagged images and remove them"""
    configuration = collector.configuration
    docker_context = configuration["harpoon"].docker_context
    images = docker_context.images()
    found = False
    for image in images:
        if image["RepoTags"] == ["<none>:<none>"]:
            found = True
            image_id = image["Id"]
            log.info("Deleting untagged image\thash=%s", image_id)
            try:
                docker_context.remove_image(image["Id"])
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

    for index, layer in enumerate(Builder().layered(configuration["images"], only_pushable=only_pushable)):
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
    collector.configuration['harpoon'].only_pushable = True
    show(collector, **kwargs)

@an_action(needs_image=True)
def print_dockerfile(collector, image, **kwargs):
    """Print a dockerfile for the specified image"""
    print('\n'.join(image.docker_file.docker_lines))

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
    docker_context = collector.configuration["harpoon"].docker_context
    collector.configuration["authentication"].login(docker_context, image, is_pushing=False, global_docker=True)

@an_action()
def write_login(collector, image, **kwargs):
    """Login to a docker registry with write permissions"""
    docker_context = collector.configuration["harpoon"].docker_context
    collector.configuration["authentication"].login(docker_context, image, is_pushing=True, global_docker=True)

# Make it so future use of @an_action doesn't result in more default tasks
info["is_default"] = False
