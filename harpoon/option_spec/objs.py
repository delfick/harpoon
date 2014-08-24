from input_algorithms.objs import objMaker
from harpoon.tasks import available_tasks

class Task(objMaker("Task", ("action", "run"), "options", "overrides", "description", ("label", "Project"))):
    def run(self, harpoon, other_args):
        """Run this task"""
        options = self.options or {}
        defaults = getattr(self, "defaults", {})

        opts = {}
        opts.update(other_args)
        opts.update(defaults)
        opts.update(options)
        return available_tasks[self.action](harpoon, **opts)

    def add_option_defaults(self, **defaults):
        """Record some default values for options"""
        if not hasattr(self, "defaults"):
            self.defaults = {}
        self.defaults.update(defaults)

