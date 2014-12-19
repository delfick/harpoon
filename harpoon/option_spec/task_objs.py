from harpoon.tasks import available_tasks
from harpoon.errors import BadOption

from input_algorithms.dictobj import dictobj
from option_merge import MergedOptions

class Task(dictobj):
    fields = [("action", "run"), ("label", "Project"), ("options", None), ("overrides", None), ("description", "")]

    def run(self, overview, cli_args, image):
        """Run this task"""
        task_func = available_tasks[self.action]
        configuration = MergedOptions.using(overview.configuration, dont_prefix=overview.configuration.dont_prefix, converters=overview.configuration.converters)

        if self.options:
            if image:
                configuration.update({"images": {image: self.options}})
            else:
                configuration.update(self.options)

        configuration.update(cli_args, source="<cli>")

        if self.overrides:
            configuration.update(self.overrides)

        images = None
        if task_func.needs_images:
            images = self.determine_image(image, overview, configuration, needs_image=task_func.needs_image)
            if image:
                image = images[image]

        if image:
            image.find_missing_env()

        return available_tasks[self.action](overview, configuration, images=images, image=image)

    def determine_image(self, image, overview, configuration, needs_image=True):
        """Complain if we don't have an image"""
        images = configuration["images"]

        available = None
        available = images.keys()

        if needs_image:
            if not image:
                info = {}
                if available:
                    info["available"] = available
                raise BadOption("Please use --image to specify an image to run /bin/bash in", **info)

            if image not in images:
                raise BadOption("No such image", wanted=image, available=images.keys())

        return images

    def specify_image(self, image):
        """Specify the image this task belongs to"""
        self.image = image

