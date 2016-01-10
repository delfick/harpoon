"""
We have here the object representing a task.

Tasks contain a reference to the functionality it provides (in ``harpoon.actions``)
as well as options that are used to override those in the image it's attached
to.
"""

from harpoon.errors import BadOption

from input_algorithms.dictobj import dictobj
from option_merge import MergedOptions

class Task(dictobj):
    """
    Used to add extra options associated with the task and to start the action
    from ``harpoon.actions``.

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
                from harpoon.actions import available_actions
            if self.action in available_actions:
                self.description = available_actions[self.action].__doc__

    def run(self, collector, image, available_actions, tasks, **extras):
        """Run this task"""
        task_func = available_actions[self.action]
        configuration = collector.configuration.wrapped()

        if self.options:
            if image:
                configuration.update({"images": {image: self.options}})
            else:
                configuration.update(self.options)

        # args like --port and the like should override what's in the options
        # But themselves be overridden by the overrides
        configuration.update(configuration["args_dict"].as_dict(), source="<args_dict>")

        if self.overrides:
            overrides = {}
            for key, val in self.overrides.items():
                overrides[key] = val
                if isinstance(val, MergedOptions):
                    overrides[key] = dict(val.items())
            configuration.update(overrides)

        if task_func.needs_image:
            self.find_image(image, configuration)
            image = configuration["images"][image]
            image.find_missing_env()

        from harpoon.collector import Collector
        new_collector = Collector()
        new_collector.configuration = configuration
        new_collector.configuration_file = collector.configuration_file
        artifact = configuration["harpoon"].artifact
        return task_func(new_collector, image=image, tasks=tasks, artifact=artifact, **extras)

    def find_image(self, image, configuration):
        """Complain if we don't have an image"""
        images = configuration["images"]
        available = list(images.keys())

        if not image:
            info = {}
            if available:
                info["available"] = available
            raise BadOption("Please use --image to specify an image", **info)

        if image not in images:
            raise BadOption("No such image", wanted=image, available=available)

