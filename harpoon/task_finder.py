"""
Responsible for finding tasks in the configuration and executing them
"""

from harpoon.actions import available_actions, default_actions
from harpoon.option_spec.task_objs import Task
from harpoon.errors import BadTask

class TaskFinder(object):
    def __init__(self, collector):
        self.tasks = {}
        self.collector = collector

    def image_finder(self, task):
        return getattr(self.tasks[task], "image", self.collector.configuration['harpoon'].chosen_image)

    def task_runner(self, task, **kwargs):
        if task not in self.tasks:
            raise BadTask("Unknown task", task=task, available=sorted(list(self.tasks.keys())))
        return self.tasks[task].run(self.collector, self.image_finder(task), available_actions, self.tasks, **kwargs)

    def default_tasks(self):
        """Return default tasks"""
        return dict((name, Task(action=name, label="Harpoon")) for name in default_actions)

    def find_tasks(self, overrides):
        """Find the custom tasks and record the associated image with each task"""
        tasks = self.default_tasks()
        configuration = self.collector.configuration

        for image in list(configuration["images"].keys()):
            path = configuration.path(["images", image, "tasks"], joined="images.{0}.tasks".format(image))
            nxt = configuration.get(path, {})
            tasks.update(nxt)

        if overrides:
            tasks.update(overrides)

        self.tasks = tasks
        return tasks

