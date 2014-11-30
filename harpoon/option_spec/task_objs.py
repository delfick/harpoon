from harpoon.tasks import available_tasks
from harpoon.errors import BadOption
from harpoon.imager import Imager

from input_algorithms.dictobj import dictobj
from option_merge import MergedOptions

class Task(dictobj):
    fields = [("action", "run"), ("label", "Project"), ("options", None), ("overrides", None), ("description", "")]

    def run(self, harpoon, cli_args):
        """Run this task"""
        task_func = available_tasks[self.action]
        image = getattr(self, "image", cli_args["harpoon"].get("chosen_image"))

        configuration = MergedOptions.using(harpoon.configuration, dont_prefix=[dictobj], converters=harpoon.configuration.converters)

        if image:
            configuration.update({"harpoon": {"chosen_image": image}})
        del cli_args["harpoon"]["chosen_image"]

        if self.options:
            if image:
                configuration.update({"images": {image: self.options}})
            else:
                configuration.update(self.options)

        configuration.update(cli_args)

        if self.overrides:
            configuration.update(self.overrides)

        imager = None
        images = None
        if task_func.needs_imager:
            imager, images = self.determine_image(harpoon, configuration, needs_image=task_func.needs_image)

        return available_tasks[self.action](harpoon, configuration, imager=imager, images=images, image=image)

    def determine_image(self, harpoon, configuration, needs_image=True):
        """Complain if we don't have an image"""
        image = configuration.get("harpoon.chosen_image")
        imager = Imager(configuration, harpoon.docker_context)

        available = None
        available = imager.images.keys()

        images = imager.images
        if needs_image:
            if image is None:
                info = {}
                if available:
                    info["available"] = available
                raise BadOption("Please use --image to specify an image to run /bin/bash in", **info)

            if image not in images:
                raise BadOption("No such image", wanted=image, available=images.keys())

        return imager, images

    def specify_image(self, image):
        """Specify the image this task belongs to"""
        self.image = image

