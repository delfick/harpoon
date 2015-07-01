"""
Collects then parses configuration files and verifies that they are valid.
"""

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.errors import BadConfiguration, BadYaml
from harpoon.processes import command_output
from harpoon.task_finder import TaskFinder
from harpoon.tasks import available_tasks

from input_algorithms.spec_base import NotSpecified
from input_algorithms.dictobj import dictobj
from input_algorithms.meta import Meta

from option_merge.collector import Collector
from option_merge import MergedOptions
from option_merge import Converter

import logging
import yaml
import six
import os

log = logging.getLogger("harpoon.collector")

class Collector(Collector):

    BadFileErrorKls = BadYaml
    BadConfigurationErrorKls = BadConfiguration

    def alter_clone_cli_args(self, new_collector, new_cli_args, new_harpoon_options=None):
        new_harpoon = self.configuration["harpoon"].clone()
        if new_harpoon_options:
            new_harpoon.update(new_harpoon_options)
        new_cli_args["harpoon"] = new_harpoon

    def find_missing_config(self, configuration):
        """Used to make sure we have images before doing anything"""
        if "images" not in self.configuration:
            raise self.BadConfigurationErrorKls("Didn't find any images in the configuration")

    def extra_prepare(self, configuration, cli_args, available_tasks):
        """Called before the configuration.converters are activated"""
        harpoon = cli_args.pop("harpoon")

        harpoon["configuration"] = configuration
        self.configuration.update(
            { "$@": harpoon.get("extra", "")
            , "bash": cli_args["bash"] or NotSpecified
            , "harpoon": harpoon
            , "command": cli_args['command'] or NotSpecified
            }
        , source = "<cli_args>"
        )

    def extra_prepare_after_activation(self, configuration, cli_args, available_tasks):
        """Called after the configuration.converters are activated"""
        task_overrides = {}
        task_finder = TaskFinder(self, cli_args)
        self.configuration.update(
            { "image_finder": task_finder.image_finder
            , "task_runner": task_finder.task_runner
            }
        , source = "<code>"
        )
        task_finder.find_tasks(task_overrides)

    def home_dir_configuration_location(self):
        return os.path.expanduser("~/.harpoon.yml")

    def start_configuration(self):
        """Create the base of the configuration"""
        return MergedOptions(dont_prefix=[dictobj])

    def read_file(self, location):
        """Read in a yaml file and return as a python object"""
        try:
            return yaml.load(open(location))
        except yaml.parser.ParserError as error:
            raise self.BadFileErrorKls("Failed to read yaml", location=location, error_type=error.__class__.__name__, error="{0}{1}".format(error.problem, error.problem_mark))

    def get_committime_or_mtime(self, location):
        """Get the commit time of some file or the modified time of of it if can't get from git"""
        date, status = command_output("git show -s --format=%at -n1 -- {0}".format(os.path.basename(location)), cwd=os.path.dirname(location))
        if status == 0 and date:
            return int(date[0])
        else:
            return os.path.getmtime(location)

    def add_configuration(self, configuration, collect_another_source, done, result, src):
        """Used to add a file to the configuration, result here is the yaml.load of the src"""

        def make_mtime_func(source):
            """Lazily calculate the mtime to avoid wasted computation"""
            return lambda: self.get_committime_or_mtime(source)

        if "images" in result and "__images_from__" in result["images"]:
            images_from_path = result["images"]["__images_from__"]

            if isinstance(images_from_path, six.string_types):
                images_from_path = [images_from_path]

            for ifp in images_from_path:

                if not ifp.startswith("/"):
                    ifp = os.path.join(os.path.dirname(src), ifp)

                if not os.path.exists(ifp) or not os.path.isdir(ifp):
                    raise self.BadConfigurationErrorKls("Specified folder for other configuration files points to a folder that doesn't exist", path="images.__images_from__", value=ifp)

                for root, dirs, files in os.walk(ifp):
                    for fle in files:
                        location = os.path.join(root, fle)
                        if fle.endswith(".yml") or fle.endswith(".yaml"):
                            collect_another_source(location, prefix=["images", os.path.splitext(os.path.basename(fle))[0]])

            del result["images"]["__images_from__"]

        result["mtime"] = make_mtime_func(src)
        configuration.update(result, dont_prefix=[dictobj], source=src)

    def extra_configuration_collection(self, configuration):
        """Hook to do any extra configuration collection or converter registration"""
        harpoon_spec = HarpoonSpec()

        for image in configuration.get('images', {}).keys():
            self.make_image_converters(image, configuration, harpoon_spec)

        def harpoon_converter(p, v):
            log.info("Converting %s", p)
            meta = Meta(p.configuration, [("harpoon", "")])
            configuration.converters.started(p)
            return harpoon_spec.harpoon_spec.normalise(meta, v)
        configuration.add_converter(Converter(convert=harpoon_converter, convert_path=["harpoon"]))

    def make_image_converters(self, image, configuration, harpoon_spec):
        """Make converters for this image and add them to the configuration"""
        def convert_image(path, val):
            log.info("Converting %s", path)
            everything = path.configuration.root().wrapped()
            meta = Meta(everything, [("images", ""), (image, "")])
            configuration.converters.started(path)

            base = path.configuration.root().wrapped()
            base.update(configuration.as_dict(ignore=["images"]))
            base.update(val.as_dict(ignore=["images"]))

            base["harpoon"] = configuration["harpoon"]
            base["configuration"] = configuration
            return harpoon_spec.image_spec.normalise(meta, base)

        converter = Converter(convert=convert_image, convert_path=["images", image])
        configuration.add_converter(converter)

        def convert_tasks(path, val):
            spec = harpoon_spec.tasks_spec(available_tasks)
            meta = Meta(path.configuration.root(), [('images', ""), (image, ""), ('tasks', "")])
            configuration.converters.started(path)
            return spec.normalise(meta, val)

        converter = Converter(convert=convert_tasks, convert_path=["images", image, "tasks"])
        configuration.add_converter(converter)

