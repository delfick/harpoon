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
    fields = {
          ("action", "run"): "The action to run with this image"
        , ("options", None): "The options to merge with the image options"
        , ("overrides", None): "The options to merge with the root configuration"
        , ("description", ""): "The description of the task"
        , ("label", "Project"): "The namespace when listing tasks"
        }

    def setup(self, *args, **kwargs):
        super(Task, self).setup(*args, **kwargs)
        self.set_description()

    def set_description(self, available_actions=None):
        if not self.description:
            if not available_actions:
                from harpoon.tasks import available_tasks as available_actions
            if self.action in available_actions:
                self.description = available_actions[self.action].__doc__

    def run(self, collector, cli_args, image, available_actions=None, tasks=None, **extras):
        """Run this task"""
        if available_actions is None:
            from harpoon.tasks import available_tasks as available_actions
        task_func = available_actions[self.action]
        configuration = MergedOptions.using(collector.configuration, dont_prefix=collector.configuration.dont_prefix, converters=collector.configuration.converters)

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
            collector.configuration.update(overrides)

        images = None
        if task_func.needs_images:
            images = self.determine_image(image, collector, configuration, needs_image=task_func.needs_image)
            if image:
                image = images[image]

        if image:
            image.find_missing_env()

        return task_func(collector, configuration, images=images, image=image, tasks=tasks, **extras)

    def determine_image(self, image, collector, configuration, needs_image=True):
        """Complain if we don't have an image"""
        images = configuration["images"]

        available = None
        available = images.keys()

        if needs_image:
            if not image:
                info = {}
                if available:
                    info["available"] = list(available)
                raise BadOption("Please use --image to specify an image", **info)

            if image not in images:
                raise BadOption("No such image", wanted=image, available=list(images.keys()))

        return images

    def specify_image(self, image):
        """Specify the image this task belongs to"""
        self.image = image

