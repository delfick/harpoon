from harpoon.errors import BadConfiguration, BadTask, BadYaml
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.processes import command_output
from harpoon.tasks import available_tasks
from harpoon.option_spec.objs import Task
from harpoon.imager import Imager

from option_merge import MergedOptions
from input_algorithms.meta import Meta
import logging
import yaml
import os

log = logging.getLogger("harpoon.executor")

class Harpoon(object):
    def __init__(self, configuration_file, docker_context, silent_build=False, interactive=True, logging_handler=None):
        self.interactive = interactive
        self.docker_context = docker_context
        self.logging_handler = logging_handler

        self.configuration = self.collect_configuration(configuration_file)
        self.configuration_folder = os.path.dirname(os.path.abspath(configuration_file))
        self.imager = Imager(self.configuration, docker_context, interactive=self.interactive, silent_build=silent_build)
        self.setup_logging_theme()

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

    ########################
    ###   THEME
    ########################

    def setup_logging_theme(self):
        """Setup a logging theme"""
        if "term_colors" not in self.configuration:
            return

        if not getattr(self, "logging_handler", None):
            log.warning("Told to set term_colors but don't have a logging_handler to change")
            return

        colors = self.configuration.get("term_colors")
        if not colors:
            return

        if colors not in ("light", "dark"):
            log.warning("Told to set colors to a theme we don't have\tgot=%s\thave=[light, dark]", colors)
            return

        # Haven't put much effort into actually working out more than just the message colour
        if colors == "light":
            self.logging_handler._column_color['%(message)s'][logging.INFO] = ('cyan', None, False)
        else:
            self.logging_handler._column_color['%(message)s'][logging.INFO] = ('blue', None, False)

    ########################
    ###   CONFIG
    ########################

    def home_dir_configuration(self):
        """Return a dictionary from ~/.harpoon.yml"""
        location = os.path.expanduser("~/.harpoon.yml")
        if not os.path.exists(location):
            return None, {}

        result = self.read_yaml(location)
        if not result:
            result = {}
        if not isinstance(result, dict):
            raise BadYaml("Expected yaml file to declare a dictionary", location=location, got=type(result))

        result["__mtime__"] = self.get_committime_or_mtime(location)
        return location, result

    def read_yaml(self, filepath):
        """Read in a yaml file"""
        try:
            if os.stat(filepath).st_size == 0:
                return {}
            return yaml.load(open(filepath))
        except yaml.parser.ParserError as error:
            raise BadYaml("Failed to read yaml", location=filepath, error_type=error.__class__.__name__, error=error.problem)

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
        result = self.read_yaml(configuration_file)
        result["__mtime__"] = self.get_committime_or_mtime(configuration_file)

        configuration = MergedOptions.using(result, source=configuration_file)
        configuration_dir = os.path.dirname(os.path.abspath(configuration_file))

        source, conf = self.home_dir_configuration()
        if conf:
            configuration.update(conf, source=source)

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
                            configuration.update({"images": {name: result}}, source=location)
                        except BadYaml as error:
                            errors.append(error)

        return configuration

    ########################
    ###   TASKS
    ########################

    def default_tasks(self):
        """Return default tasks"""
        def t(name, description, action=None, **options):
            if not action:
                action = name
            return (name, Task(action, description=description, options=options, label="Harpoon"))
        return dict([
              t("ssh", "Run bash in one of the containers", command="/bin/bash", action="run")
            , t("run", "Run a command in one of the containers")

            , t("make", "Make one of the images")
            , t("make_all", "Make all of the images")
            , t("make_pushable", "Make only the pushable images and their dependencies")

            , t("pull", "Pull one of the images")
            , t("pull_all", "Pull all of the images")

            , t("push", "Push one of the images")
            , t("push_all", "Push all of the images")

            , t("show", "Show the available images")
            , t("show_pushable", "Show the layers for only the pushable images")

            , t("list_tasks", "List the available tasks")
            , t("delete_untagged", "Delete untagged images")
            ])

    def interpret_tasks(self, configuration, path):
        """Find the tasks in the specified key"""
        if path not in configuration:
            return {}

        found = configuration.get(path)
        tasks = HarpoonSpec().tasks_spec(available_tasks).normalise(Meta(configuration, path), found)

        for key, task in tasks.items():
            if task.options:
                task_path = "{0}.{1}".format(path, key)
                formatter = lambda s: MergedOptionStringFormatter(self.configuration, task_path, value=s).format()
                task.options = dict((k, formatter(v)) for k, v in task.options.items())

        return tasks

    def find_tasks(self, configuration=None):
        """Find some tasks"""
        if configuration is None:
            configuration = self.configuration

        tasks = self.default_tasks()
        tasks.update(self.interpret_tasks(configuration, "tasks"))
        for image in list(configuration["images"]):
            nxt = self.interpret_tasks(configuration, ["images", image, "tasks"])
            for task in nxt.values():
                task.add_option_defaults(image=image)
            tasks.update(nxt)

        return tasks

