from harpoon.tasks import available_tasks
from harpoon.errors import BadOption
from harpoon.imager import Imager

from input_algorithms.dictobj import dictobj
from option_merge import MergedOptions

class Task(dictobj):
    fields = [("action", "run"), ("label", "Project"), ("options", None), ("overrides", None), ("description", "")]

    def run(self, overview, cli_args, image):
        """Run this task"""
        task_func = available_tasks[self.action]
        configuration = MergedOptions.using(overview.configuration, dont_prefix=[dictobj], converters=overview.configuration.converters)

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
            imager, images = self.determine_image(image, overview, configuration, needs_image=task_func.needs_image)

        if image:
            images[image].image_configuration.find_missing_env()

        return available_tasks[self.action](overview, configuration, imager=imager, images=images, image=image)

    def determine_image(self, image, overview, configuration, needs_image=True):
        """Complain if we don't have an image"""
        imager = Imager(configuration, overview.docker_context)

        available = None
        available = imager.images.keys()

        images = imager.images
        if needs_image:
            if not image:
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

