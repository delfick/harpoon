from harpoon.tasks import available_tasks
from harpoon.errors import BadOption
from harpoon.imager import Imager

from option_merge import MergedOptions
from namedlist import namedlist

import time

class Task(namedlist("Task", [("action", "run"), ("label", "Project"), ("options", None), ("overrides", None), ("description", "")])):
    def run(self, harpoon, cli_args):
        """Run this task"""
        task_func = available_tasks[self.action]
        configuration = MergedOptions.using(harpoon.configuration)

        image = getattr(self, "image", cli_args["harpoon"].get("chosen_image"))
        if image:
            configuration.update({"harpoon": {"chosen_image": image}})
        del cli_args["harpoon"]["chosen_image"]

        imager = None
        images = None
        image_name = None
        if task_func.needs_imager:
            imager, images, image_name = self.determine_image(harpoon, configuration, needs_image=task_func.needs_image)

        if image_name:
            conf = images[image_name].configuration
        else:
            conf = configuration

        if self.options:
            conf.update(self.options)

        configuration.update(cli_args)

        if self.overrides:
            configuration.update(self.overrides)

        return available_tasks[self.action](harpoon, conf, imager=imager, images=images, image=image_name)

    def determine_image(self, harpoon, configuration, needs_image=True):
        """Complain if we don't have an image"""
        image = configuration.get("harpoon.chosen_image")
        imager = Imager(configuration, harpoon.docker_context)

        available = None
        try:
            available = imager.images.keys()
        except:
            pass

        images = imager.images

        if needs_image:
            if image is None:
                info = {}
                if available:
                    info["available"] = available
                raise BadOption("Please use --image to specify an image to run /bin/bash in", **info)

            if image not in images:
                raise BadOption("No such image", wanted=image, available=images.keys())

        return imager, images, image

    def specify_image(self, image):
        """Specify the image this task belongs to"""
        self.image = image

