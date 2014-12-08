from harpoon.errors import BadOption
from harpoon.imager import Imager

from docker.errors import APIError as DockerAPIError
import itertools
import logging

log = logging.getLogger("harpoon.tasks")

available_tasks = {}
class a_task(object):
    def __init__(self, needs_image=False, needs_imager=False):
        self.needs_image = needs_image
        self.needs_imager = needs_image or needs_imager

    def __call__(self, func):
        available_tasks[func.__name__] = func
        func.needs_image = self.needs_image
        func.needs_imager = self.needs_imager
        return func

@a_task(needs_image=True)
def push(harpoon, configuration, imager, images, image):
    """Push an image"""
    pushable = dict((image, instance) for image, instance in images.items() if instance.formatted("image_index", default=None))
    if image not in pushable:
        raise BadOption("The chosen image does not have a image_index configuration", wanted=image, available=pushable.keys())
    imager.make_image(image)
    pushable[image].push()

@a_task(needs_imager=True)
def push_all(harpoon, configuration, **kwargs):
    """Push all the images"""
    configuration.update({"harpoon": {"do_push": True, "only_pushable": True}})
    make_all(harpoon, configuration, **kwargs)

@a_task(needs_image=True)
def pull(harpoon, configuration, images, image, **kwargs):
    """Pull an image"""
    ignore_missing = configuration.get("harpoon.ignore_missing", False)

    pullable = dict((image, instance) for image, instance in images.items() if instance.formatted("image_index", default=None))
    if image not in pullable:
        raise BadOption("The chosen image does not have a image_index configuration", wanted=image, available=pullable.keys())
    pullable[image].pull(ignore_missing=ignore_missing)

@a_task(needs_imager=True)
def pull_all(harpoon, configuration, imager, **kwargs):
    """Pull all the images"""
    ignore_missing = configuration.get("harpoon.ignore_missing", False)
    for layer in imager.layered(only_pushable=True):
        for image_name, image in layer:
            log.info("Pulling %s", image_name)
            image.pull(ignore_missing=ignore_missing)

@a_task(needs_image=True)
def make(harpoon, configuration, imager, images, image):
    """Just create an image"""
    imager.make_image(image)
    print("Created image {0}".format(images[image].image_name))

@a_task(needs_imager=True)
def make_all(harpoon, configuration, imager, **kwargs):
    """Creates all the images in layered order"""
    push = configuration.get("harpoon.do_push", False)
    only_pushable = configuration.get("harpoon.only_pushable", False)
    if push:
        only_pushable = True

    for layer in imager.layered(only_pushable=only_pushable):
        for image_name, image in layer:
            imager.make_image(image_name, ignore_deps=True)
            print("Created image {0}".format(image.image_name))
            if push and image.formatted("image_index", default=None):
                image.push()

@a_task(needs_imager=True)
def make_pushable(harpoon, configuration, **kwargs):
    """Make only the pushable images and their dependencies"""
    configuration.update({"harpoon": {"do_push": False, "only_pushable": True}})
    make_all(harpoon, configuration, **kwargs)

@a_task(needs_image=True)
def run(harpoon, configuration, imager, image, **kwargs):
    """Run specified task in this image"""
    imager.run(image, configuration)

@a_task()
def list_tasks(harpoon, configuration, **kwargs):
    """List the available_tasks"""
    print("Available tasks to choose from are:")
    print("Use the --task option to choose one")
    print("")
    keygetter = lambda item: item[1].label
    tasks = sorted(harpoon.find_tasks().items(), key=keygetter)
    for label, items in itertools.groupby(tasks, keygetter):
        print("--- {0}".format(label))
        print("----{0}".format("-" * len(label)))
        sorted_tasks = sorted(list(items), key=lambda item: len(item[0]))
        max_length = max(len(name) for name, _ in sorted_tasks)
        for key, task in sorted_tasks:
            print("\t{0}{1} :-: {2}".format(" " * (max_length-len(key)), key, task.description or ""))
        print("")

@a_task()
def delete_untagged(harpoon, configuration, **kwargs):
    """Find the untagged images and remove them"""
    images = harpoon.docker_context.images()
    found = False
    for image in images:
        if image["RepoTags"] == ["<none>:<none>"]:
            found = True
            image_id = image["Id"]
            log.info("Deleting untagged image\thash=%s", image_id)
            try:
                harpoon.docker_context.remove_image(image["Id"])
            except DockerAPIError as error:
                log.error("Failed to delete image\thash=%s\terror=%s", image_id, error)

    if not found:
        log.info("Didn't find any untagged images to delete!")

@a_task(needs_imager=True)
def show(harpoon, configuration, imager, **kwargs):
    """Show what images we have"""
    flat = configuration.get("harpoon.flat", False)
    only_pushable = configuration.get("harpoon.only_pushable", False)

    for index, layer in enumerate(imager.layered(only_pushable=only_pushable)):
        if flat:
            for _, image in layer:
                print(image.image_name)
        else:
            print("Layer {0}".format(index))
            for _, image in layer:
                print("    {0}".format(image.image_configuration.display_line()))
            print("")

@a_task(needs_imager=True)
def show_pushable(harpoon, configuration, **kwargs):
    """Show what images we have"""
    configuration.update({"harpoon": {'only_pushable': True}})
    show(harpoon, configuration, **kwargs)

