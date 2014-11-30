from harpoon.errors import BadConfiguration, BadTask, BadYaml
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.option_spec.task_objs import Task
from harpoon.processes import command_output
from harpoon.tasks import available_tasks

from input_algorithms.dictobj import dictobj
from option_merge import MergedOptions
from input_algorithms.meta import Meta
from option_merge import Converter
from itertools import chain
import logging
import yaml
import os

log = logging.getLogger("harpoon.executor")

class Harpoon(object):
    def __init__(self, configuration_file, docker_context, logging_handler=None):
        self.docker_context = docker_context
        self.logging_handler = logging_handler

        self.configuration = self.collect_configuration(configuration_file)
        self.configuration_folder = os.path.dirname(os.path.abspath(configuration_file))
        self.setup_logging_theme()

    def start(self, cli_args):
        """Do the harpooning"""
        if "images" not in self.configuration:
            raise BadConfiguration("Didn't find any images in the configuration")

        self.configuration.update(
            { "$@": cli_args["harpoon"].get("extra", "")
            , "config_root" : self.configuration_folder
            }
        )

        tasks = self.find_tasks()
        task = cli_args["harpoon"]["chosen_task"]
        if task not in tasks:
            raise BadTask("Unknown task", task=task, available=tasks.keys())

        tasks[task].run(self, cli_args)

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
        configuration_dir = os.path.dirname(os.path.abspath(configuration_file))

        images_from = []
        images_from_path = None
        if "images" in result and "__images_from__" in result["images"]:
            images_from_path = result["images"]["__images_from__"]

            if not images_from_path.startswith("/"):
                images_from_path = os.path.join(configuration_dir, images_from_path)

            if not os.path.exists(images_from_path) or not os.path.isdir(images_from_path):
                raise BadConfiguration("Specified folder for other configuration files points to a folder that doesn't exist", path="images.__images_from__", value=images_from_path)

            images_from = sorted(chain.from_iterable([
                  [os.path.join(root, fle) for fle in files if fle.endswith(".yml") or fle.endswith(".yaml")]
                  for root, dirs, files in os.walk(images_from_path)
                ]))

        harpoon_spec = HarpoonSpec()
        configuration = MergedOptions(dont_prefix=[dictobj])

        home_dir_configuration = os.path.expanduser("~/.harpoon.yml")
        sources = [home_dir_configuration, configuration_file] + images_from

        def make_mtime_func(source):
            return lambda: self.get_committime_or_mtime(source)

        for source in sources:
            if source is None or not os.path.exists(source):
                continue

            try:
                result = self.read_yaml(source)
            except BadYaml as error:
                errors.append(error)
                continue

            if "images" in result and "__images_from__" in result["images"]:
                del result["images"]["__images_from__"]

            if source in images_from:
                result = {"images": {os.path.splitext(os.path.basename(source))[0]: result}}

            result["__mtime__"] = make_mtime_func(source)

            if "images" in result:
                images = result.pop("images")
                images = dict(
                      (image, MergedOptions.using(configuration.root(), val, converters=configuration.converters))
                      for image, val in images.items()
                    )
                result["images"] = images

            configuration.update(result, dont_prefix=[dictobj], source=source)

            for image in result.get('images', {}).keys():
                self.make_converters(image, configuration, harpoon_spec)

        if errors:
            raise BadConfiguration("Some of the configuration was broken", _errors=errors)

        for converter in configuration.converters:
            configuration.add_converter(converter)

        configuration.converters.activate()

        return configuration

    def make_converters(self, image, configuration, harpoon_spec):
        """Make converters for this image and add them to the configuration"""
        def convert_image(path, val):
            spec = harpoon_spec.image_spec
            everything = MergedOptions.using(path.configuration.root(), converters=configuration.converters)

            meta = Meta(everything, [("images", ""), (image, "")])
            meta.result = {}
            configuration.converters.done(path, meta.result)

            for key, v in val.items(ignore_converters=True):
                meta.result[key] = v
            return spec.normalise(meta, meta.result)

        converter = Converter(convert=convert_image, convert_path=["images", image])
        configuration.converters.append(converter)

        def convert_tasks(path, val):
            spec = harpoon_spec.tasks_spec(available_tasks)
            meta = Meta(path.configuration.root(), [('images', ""), (image, ""), ('tasks', "")])
            return spec.normalise(meta, val)

        converter = Converter(convert=convert_tasks, convert_path=["images", image, "tasks"])
        configuration.converters.append(converter)

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

        for key, task in found.items():
            if task.options:
                task_path = "{0}.{1}".format(path, key)
                formatter = lambda s: MergedOptionStringFormatter(self.configuration, task_path, value=s).format()
                task.options = dict((k, formatter(v)) for k, v in task.options.items())

        return dict(found.items())

    def find_tasks(self, configuration=None):
        """Find some tasks"""
        if configuration is None:
            configuration = self.configuration

        tasks = self.default_tasks()
        tasks.update(self.interpret_tasks(configuration, "tasks"))
        for image in list(configuration["images"]):
            nxt = self.interpret_tasks(configuration, configuration.path(["images", image, "tasks"], joined="images.{0}.tasks".format(image)))
            for task in nxt.values():
                task.specify_image(image)
            tasks.update(nxt)

        return tasks

