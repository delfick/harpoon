"""
The functionality itself for each task.

Each task is specified with the ``a_task`` decorator and indicates whether it's
necessary to provide the task with the object containing all the images and/or
one specific image object.
"""
from harpoon.ship.builder import Builder
from harpoon.ship.syncer import Syncer
from harpoon.errors import BadOption

from docker.errors import APIError as DockerAPIError
import itertools
import logging

log = logging.getLogger("harpoon.tasks")

available_tasks = {}
class a_task(object):
    """Records a task in the ``available_tasks`` dictionary"""
    def __init__(self, needs_image=False, needs_images=False):
        self.needs_image = needs_image
        self.needs_images = needs_image or needs_images

    def __call__(self, func):
        available_tasks[func.__name__] = func
        func.needs_image = self.needs_image
        func.needs_images = self.needs_images
        return func

@a_task(needs_image=True)
def push(overview, configuration, images, image):
    """Push an image"""
    if not image.image_index:
        raise BadOption("The chosen image does not have a image_index configuration", wanted=image.name)
    Builder().make_image(image, images)
    Syncer().push(image)

@a_task(needs_images=True)
def push_all(overview, configuration, **kwargs):
    """Push all the images"""
    configuration["harpoon"].do_push = True
    configuration["harpoon"].only_pushable = True
    make_all(overview, configuration, **kwargs)

@a_task(needs_image=True)
def pull(overview, configuration, images, image, **kwargs):
    """Pull an image"""
    if not image.image_index:
        raise BadOption("The chosen image does not have a image_index configuration", wanted=image.name)
    Syncer().pull(image, ignore_missing=image.harpoon.ignore_missing)

@a_task(needs_images=True)
def pull_all(overview, configuration, images, **kwargs):
    """Pull all the images"""
    for layer in Builder().layered(images, only_pushable=True):
        for image_name, image in layer:
            log.info("Pulling %s", image_name)
            Syncer().pull(image, ignore_missing=image.harpoon.ignore_missing)

@a_task(needs_image=True)
def make(overview, configuration, images, image):
    """Just create an image"""
    Builder().make_image(image, images)
    print("Created image {0}".format(image.image_name))

@a_task(needs_images=True)
def make_all(overview, configuration, images, **kwargs):
    """Creates all the images in layered order"""
    push = configuration["harpoon"].do_push
    only_pushable = configuration["harpoon"].only_pushable
    if push:
        only_pushable = True

    for layer in Builder().layered(images, only_pushable=only_pushable):
        for _, image in layer:
            Builder().make_image(image, images, ignore_deps=True, ignore_parent=True)
            print("Created image {0}".format(image.image_name))
            if push and image.image_index:
                Syncer().push(image)

@a_task(needs_images=True)
def make_pushable(overview, configuration, **kwargs):
    """Make only the pushable images and their dependencies"""
    configuration["harpoon"].do_push = True
    configuration["harpoon"].only_pushable = True
    make_all(overview, configuration, **kwargs)

@a_task(needs_image=True)
def run(overview, configuration, images, image, **kwargs):
    """Run specified task in this image"""
    image.build_and_run(images)

@a_task()
def list_tasks(overview, configuration, **kwargs):
    """List the available_tasks"""
    print("Available tasks to choose from are:")
    print("Use the --task option to choose one")
    print("")
    keygetter = lambda item: item[1].label
    tasks = sorted(overview.find_tasks().items(), key=keygetter)
    for label, items in itertools.groupby(tasks, keygetter):
        print("--- {0}".format(label))
        print("----{0}".format("-" * len(label)))
        sorted_tasks = sorted(list(items), key=lambda item: len(item[0]))
        max_length = max(len(name) for name, _ in sorted_tasks)
        for key, task in sorted_tasks:
            print("\t{0}{1} :-: {2}".format(" " * (max_length-len(key)), key, task.description or ""))
        print("")

@a_task()
def delete_untagged(overview, configuration, **kwargs):
    """Find the untagged images and remove them"""
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

@a_task(needs_images=True)
def show(overview, configuration, images, **kwargs):
    """Show what images we have"""
    flat = configuration.get("harpoon.flat", False)
    only_pushable = configuration.get("harpoon.only_pushable", False)

    for index, layer in enumerate(Builder().layered(images, only_pushable=only_pushable)):
        if flat:
            for _, image in layer:
                print(image.image_name)
        else:
            print("Layer {0}".format(index))
            for _, image in layer:
                print("    {0}".format(image.display_line()))
            print("")

@a_task(needs_images=True)
def show_pushable(overview, configuration, **kwargs):
    """Show what images we have"""
    configuration['harpoon'].only_pushable = True
    show(overview, configuration, **kwargs)

