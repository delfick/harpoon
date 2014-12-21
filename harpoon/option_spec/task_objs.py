"""
We have here the object representing a task.

Tasks contain a reference to the functionality it provides (in ``harpoon.tasks``)
as well as options that are used to override those in the image it's attached
to.
"""

from harpoon.errors import BadOption

from input_algorithms.dictobj import dictobj
from option_merge import MergedOptions

class Task(dictobj):
    """
    Used to add extra options associated with the task and to start the action
    from ``harpoon.tasks``.

    Also responsible for complaining if the specified action doesn't exist.

    Will also ask the image to complain about any missing environment variables.
    """
    fields = [("action", "run"), ("label", "Project"), ("options", None), ("overrides", None), ("description", "")]

    def run(self, overview, cli_args, image, available_tasks=None):
        """Run this task"""
        if available_tasks is None:
            from harpoon.tasks import available_tasks
        task_func = available_tasks[self.action]
        configuration = MergedOptions.using(overview.configuration, dont_prefix=overview.configuration.dont_prefix, converters=overview.configuration.converters)

        if self.options:
            if image:
                configuration.update({"images": {image: self.options}})
            else:
                configuration.update(self.options)

        configuration.update(cli_args, source="<cli>")

        if self.overrides:
            overrides = {}
            for key, val in self.overrides.items():
                overrides[key] = val
                if isinstance(val, MergedOptions):
                    overrides[key] = dict(val.items())
            overview.configuration.update(overrides)

        images = None
        if task_func.needs_images:
            images = self.determine_image(image, overview, configuration, needs_image=task_func.needs_image)
            if image:
                image = images[image]

        if image:
            image.find_missing_env()

        return task_func(overview, configuration, images=images, image=image)

    def determine_image(self, image, overview, configuration, needs_image=True):
        """Complain if we don't have an image"""
        images = configuration["images"]

        available = None
        available = images.keys()

        if needs_image:
            if not image:
                info = {}
                if available:
                    info["available"] = list(available)
                raise BadOption("Please use --image to specify an image to run /bin/bash in", **info)

            if image not in images:
                raise BadOption("No such image", wanted=image, available=list(images.keys()))

        return images

    def specify_image(self, image):
        """Specify the image this task belongs to"""
        self.image = image

