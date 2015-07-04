"""
Responsible for finding tasks in the configuration and executing them
"""

from harpoon.tasks import available_tasks, default_tasks
from harpoon.option_spec.task_objs import Task
from harpoon.errors import BadTask

class TaskFinder(object):
    def __init__(self, collector, cli_args=None):
        self.tasks = {}
        if cli_args is None:
            cli_args = {}
        self.cli_args = cli_args
        self.collector = collector
        self.configuration = self.collector.configuration

    def image_finder(self, task):
        return getattr(self.tasks[task], "image", self.configuration['harpoon'].chosen_image)

    def task_runner(self, task, **kwargs):
        if task not in self.tasks:
            raise BadTask("Unknown task", task=task, available=sorted(list(self.tasks.keys())))
        return self.tasks[task].run(self.collector, self.cli_args, self.image_finder(task), available_actions=available_tasks, tasks=self.tasks, **kwargs)

    def default_tasks(self):
        """Return default tasks"""
        return dict((name, Task(action=name, label="Harpoon")) for name in default_tasks)

    def find_tasks(self, overrides):
        """Find the custom tasks and record the associated image with each task"""
        tasks = self.default_tasks()
        configuration = self.configuration

        for image in list(configuration["images"]):
            path = configuration.path(["images", image, "tasks"], joined="images.{0}.tasks".format(image))
            nxt = configuration.get(path, {})
            for task in nxt.values():
                task.specify_image(image)
            tasks.update(nxt)

        if overrides:
            tasks.update(overrides)

        self.tasks = tasks
        return tasks

