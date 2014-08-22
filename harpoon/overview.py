from harpoon.errors import BadConfiguration, BadTask, NoSuchTask, BadYaml
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.processes import command_output
from harpoon.tasks import available_tasks
from harpoon.imager import Imager

from option_merge import MergedOptions
import yaml
import os

class Task(object):
    def __init__(self, func, args=None, kwargs=None, description=None, label="Harpoon"):
        self.func = func
        self.args = args
        self.label = label
        self.kwargs = kwargs
        self.description = description

    def run(self, harpoon, other_args):
        """Run this task"""
        args = self.args
        kwargs = self.kwargs
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        opts = other_args
        opts.update(kwargs)
        return self.func(harpoon, *args, **opts)

class Harpoon(object):
    def __init__(self, configuration_file, docker_context, silent_build=False, interactive=True):
        self.interactive = interactive
        self.docker_context = docker_context

        self.configuration = self.collect_configuration(configuration_file)
        self.configuration_folder = os.path.dirname(os.path.abspath(configuration_file))
        self.imager = Imager(self.configuration, docker_context, interactive=self.interactive, silent_build=silent_build)

    def start(self, task, extra=None, keep_replaced=False, no_intervention=False, env=None, ports=None, **kwargs):
        """Do the harpooning"""
        if not self.configuration.get("images"):
            raise BadConfiguration("Didn't find any images in the configuration")

        if extra is None:
            extra = ""
        self.configuration["$@"] = extra
        self.configuration["config_root"] = self.configuration_folder

        if "harpoon" not in self.configuration:
            self.configuration["harpoon"] = {}

        for (name, val) in [
            ("env", env), ("ports", ports), ("keep_replaced", keep_replaced), ("no_intervention", no_intervention)
        ]:
            self.configuration["harpoon"][name] = val or self.configuration["harpoon"].get(name)

        tasks = self.find_tasks()
        if task not in tasks:
            raise BadTask("Unknown task", task=task, available=tasks.keys())

        tasks[task].run(self, kwargs)

    def get_committime_or_mtime(self, location):
        """Get the commit time of some file or the modified time of of it if can't get from git"""
        date, status = command_output("git show -s --format=%at -n1 -- {0}".format(os.path.basename(location)), cwd=os.path.dirname(location))
        if status == 0 and date:
            return int(date[0])
        else:
            return os.path.getmtime(location)

    def collect_configuration(self, configuration_file):
        """Return us a MergedOptions with this configuration and any collected configurations"""
        errors = []
        collected = []
        result = self.read_yaml(configuration_file)
        result["__mtime__"] = self.get_committime_or_mtime(configuration_file)

        configuration = MergedOptions.using(result)
        configuration_dir = os.path.dirname(os.path.abspath(configuration_file))
        if "images.__images_from__" in configuration:
            images_from = MergedOptionStringFormatter(configuration, "images.__images_from__").format()
            del configuration["images.__images_from__"]

            if not images_from.startswith("/"):
                images_from = os.path.join(configuration_dir, images_from)

            if not os.path.exists(images_from) or not os.path.isdir(images_from):
                raise BadConfiguration("Specified folder for other configuration files points to a folder that doesn't exist", path="images.__images_from__", value=images_from)

            for root, dirs, files in os.walk(images_from):
                for fle in files:
                    if fle.endswith(".yml") or fle.endswith(".yaml"):
                        location = os.path.join(root, fle)
                        try:
                            name = os.path.splitext(fle)[0]
                            result = self.read_yaml(location)
                            result["__mtime__"] = self.get_committime_or_mtime(location)
                            collected.append({"images": {name: result}})
                        except BadYaml as error:
                            errors.append(error)

        return MergedOptions.using(configuration, *collected)

    def read_yaml(self, filepath):
        """Read in a yaml file"""
        try:
            if os.stat(filepath).st_size == 0:
                return {}
            return yaml.load(open(filepath))
        except yaml.parser.ParserError as error:
            raise BadYaml("Failed to read yaml", location=filepath, error_type=error.__class__.__name__, error=error.problem)

    def default_tasks(self):
        """Return default tasks"""
        return {
              "ssh": Task(available_tasks["run_task"], kwargs={"command":"/bin/bash"}, description="Run bash in one of the containers")
            , "run": Task(available_tasks["run_task"], description="Run a command in one of the containers")

            , "make": Task(available_tasks["make"], description="Make one of the images")
            , "make_all": Task(available_tasks["make_all"], description="Make all of the images")
            , "make_pushable": Task(available_tasks["make_pushable"], description="Make only the pushable images and their dependencies")

            , "pull": Task(available_tasks["pull"], description="Pull one of the images")
            , "pull_all": Task(available_tasks["pull_all"], description="Pull all of the images")

            , "push": Task(available_tasks["push"], description="Push one of the images")
            , "push_all": Task(available_tasks["push_all"], description="Push all of the images")

            , "show": Task(available_tasks["show"], description="Show the available images")
            , "show_pushable": Task(available_tasks["show_pushable"], description="Show the layers for only the pushable images")

            , "list_tasks": Task(available_tasks["list_tasks"], description="List the available tasks")
            , "delete_untagged": Task(available_tasks["delete_untagged"], description="Delete untagged images")
            }

    def interpret_tasks(self, configuration, image, path):
        """Find the tasks in the specified key"""
        errors = []
        if path not in configuration:
            return {}

        tasks = {}
        found = configuration.get(path)
        if not isinstance(found, dict) and not isinstance(found, MergedOptions):
            raise BadTask("Tasks are not a dictionary", path=path, found=type(found))

        for key, val in found.items():
            args = None
            label = "Project"
            kwargs = None
            task_path = "{0}.{1}".format(path, key)
            description = ""
            if isinstance(val, dict) or isinstance(val, MergedOptions):
                label = val.get("label", label)
                description = val.get("description", "")

                if "options" in val and "spec" in val:
                    raise BadTask("Dictionary task must specify spec or options, not both", found=val.keys())

                if "options" in val:
                    val = ["run_task", [], val["options"]]
                else:
                    val = val.get("spec", "run_task")

            if isinstance(val, basestring):
                task_name = val
            elif isinstance(val, list):
                if len(val) == 1:
                    task_name = val
                elif len(val) == 2:
                    task_name, args = val
                elif len(val) == 3:
                    task_name, args, kwargs = val

            if task_name not in available_tasks:
                errors.append(NoSuchTask(task=val, path=task_path, available=available_tasks.keys()))
            else:
                if args is None:
                    args = ()
                if kwargs is None:
                    kwargs = {}

                task_path = "{0}.{1}".format(path, key)
                formatter = lambda s: MergedOptionStringFormatter(self.configuration, task_path, value=s).format()
                args = [formatter(arg) for arg in args]
                kwargs = dict((key, formatter(val)) for key, val in kwargs.items())

                if image not in kwargs and image is not None:
                    kwargs['image'] = image
                tasks[key] = Task(available_tasks[task_name], args, kwargs, description=description, label=label)

        if errors:
            raise BadTask(path=path, _errors=errors)

        return tasks

    def find_tasks(self, configuration=None):
        """Find some tasks"""
        if configuration is None:
            configuration = self.configuration

        tasks = self.default_tasks()
        tasks.update(self.interpret_tasks(configuration, None, "tasks"))
        for image in configuration["images"]:
            tasks.update(self.interpret_tasks(configuration, image, "images.{0}.tasks".format(image)))
        return tasks

