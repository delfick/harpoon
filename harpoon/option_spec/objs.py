from input_algorithms.objs import objMaker
from harpoon.tasks import available_tasks

class Task(objMaker("Task", ("action", "run"), "options", "overrides", "description", ("label", "Project"))):
    def run(self, harpoon, other_args):
        """Run this task"""
        options = self.options
        if options is None:
            options = {}
        opts = dict(other_args)
        opts.update(options)
        return available_tasks[self.action](harpoon, **opts)

