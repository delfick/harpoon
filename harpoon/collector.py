"""
The collector is responsible for collecting configuration and harpoon
modules.

.. autoclass:: harpoon.collector.Collector
"""

from harpoon.option_spec.harpoon_specs import HarpoonSpec
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.errors import BadYaml, BadConfiguration
from harpoon.option_spec.task_objs import Task
from harpoon.actions import available_actions
from harpoon.task_finder import TaskFinder

from input_algorithms.spec_base import NotSpecified
from input_algorithms import spec_base as sb
from input_algorithms.dictobj import dictobj
from input_algorithms.meta import Meta

from option_merge_addons import Result, Addon, Register, AddonGetter
from option_merge.collector import Collector
from option_merge import MergedOptions
from option_merge import Converter

from delfick_app import command_output
import logging
import yaml
import six
import os

log = logging.getLogger("harpoon.collector")

class Collector(Collector):
    """
    This is based off
    http://option-merge.readthedocs.io/en/latest/docs/api/collector.html

    It overrides the following:

    .. automethod:: harpoon.collector.Collector.extra_prepare

    .. automethod:: harpoon.collector.Collector.extra_configuration_collection

    .. automethod:: harpoon.collector.Collector.extra_prepare_after_activation

    .. automethod:: harpoon.collector.Collector.add_configuration
    """
    _merged_options_formattable = True

    BadFileErrorKls = BadYaml
    BadConfigurationErrorKls = BadConfiguration

    def setup(self):
        self.task_overrides = {}

    def alter_clone_args_dict(self, new_collector, new_args_dict, options=None):
        return MergedOptions.using(
              new_args_dict
            , {"harpoon": self.configuration["harpoon"].as_dict()}
            , options or {}
            )

    def extra_prepare(self, configuration, args_dict):
        """
        Called before the configuration.converters are activated

        Here we make sure that we have harpoon options from ``args_dict`` in
        the configuration.

        We then load all the harpoon modules as specified by the
        ``harpoon.addons`` setting.

        Finally we inject into the configuration:

        $@
            The ``harpoon.extra`` setting

        bash
            The ``bash`` setting

        command
            The ``command`` setting

        harpoon
            The harpoon settings

        collector
            This instance
        """
        harpoon = self.find_harpoon_options(configuration, args_dict)
        self.register = self.setup_addon_register(harpoon)

        # Make sure images is started
        if "images" not in self.configuration:
            self.configuration["images"] = {}

        # Add our special stuff to the configuration
        self.configuration.update(
            { "$@": harpoon.get("extra", "")
            , "bash": args_dict["bash"] or sb.NotSpecified
            , "harpoon": harpoon
            , "assume_role": args_dict["assume_role"] or NotSpecified
            , "command": args_dict['command'] or sb.NotSpecified
            , "collector": self
            }
        , source = "<args_dict>"
        )

    def find_harpoon_options(self, configuration, args_dict):
        """Return us all the harpoon options"""
        d = lambda r: {} if r in (None, "", NotSpecified) else r
        return MergedOptions.using(
              dict(d(configuration.get('harpoon')).items())
            , dict(d(args_dict.get("harpoon")).items())
            ).as_dict()

    def setup_addon_register(self, harpoon):
        """Setup our addon register"""
        # Create the addon getter and register the crosshairs namespace
        self.addon_getter = AddonGetter()
        self.addon_getter.add_namespace("harpoon.crosshairs", Result.FieldSpec(), Addon.FieldSpec())

        # Initiate the addons from our configuration
        register = Register(self.addon_getter, self)

        if "addons" in harpoon:
            addons = harpoon["addons"]
            if type(addons) in (MergedOptions, dict) or getattr(addons, "is_dict", False):
                spec = sb.dictof(sb.string_spec(), sb.listof(sb.string_spec()))
                meta = Meta(harpoon, []).at("addons")
                for namespace, adns in spec.normalise(meta, addons).items():
                    register.add_pairs(*[(namespace, adn) for adn in adns])

        # Import our addons
        register.recursive_import_known()

        # Resolve our addons
        register.recursive_resolve_imported()

        return register

    def extra_prepare_after_activation(self, configuration, args_dict):
        """
        Called after the configuration.converters are activated

        Here we create our ``task_maker`` helper that we pass into ``post_register``
        for our ``option_merge_addon_hook`` functions.

        We also create a ``task_finder`` for doing task finding related duties.
        """
        def task_maker(name, description=None, action=None, label="Project", **options):
            if not action:
                action = name
            self.task_overrides[name] = Task(action=action, description=description, options=options, label=label)
            return self.task_overrides[name]

        # Post register our addons
        extra_args = {"harpoon.crosshairs": {"task_maker": task_maker}}
        self.register.post_register(extra_args)

        # Make the task finder
        task_finder = TaskFinder(self)
        configuration["task_runner"] = task_finder.task_runner
        task_finder.find_tasks(self.task_overrides)

    def home_dir_configuration_location(self):
        return os.path.expanduser("~/.harpoonrc.yml")

    def start_configuration(self):
        """Create the base of the configuration"""
        return MergedOptions(dont_prefix=[dictobj])

    def read_file(self, location):
        """Read in a yaml file and return as a python object"""
        try:
            return yaml.load(open(location))
        except (yaml.parser.ParserError, yaml.scanner.ScannerError) as error:
            raise self.BadFileErrorKls("Failed to read yaml"
                , location=location
                , error_type=error.__class__.__name__
                , error="{0}{1}".format(error.problem, error.problem_mark)
                )

    def get_committime_or_mtime(self, context, location):
        """Get the commit time of some file or the modified time of of it if can't get from git"""
        status, date = 0, None
        if context.use_git:
            date, status = command_output("git show -s --format=%at -n1 -- {0}".format(os.path.basename(location)), cwd=os.path.dirname(location))
        if status == 0 and date:
            return int(date[0])
        else:
            return os.path.getmtime(location)

    def add_configuration(self, configuration, collect_another_source, done, result, src):
        """
        Used to add a file to the configuration, result here is the yaml.load
        of the src.

        If the configuration we're reading in has ``harpoon.extra_files``
        then this is treated as a list of strings of other files to collect.

        We also take extra files to collector from result["images"]["__images_from__"]
        """
        def make_mtime_func(source):
            """Lazily calculate the mtime to avoid wasted computation"""
            return lambda context: self.get_committime_or_mtime(context, source)

        # Make sure to maintain the original config_root
        if "config_root" in configuration:
            # if we already have a config root then we only keep new config root if it's not the home location
            # i.e. if it is the home configuration, we don't delete the new config_root
            if configuration["config_root"] != os.path.dirname(self.home_dir_configuration_location()):
                if "config_root" in result:
                    del result["config_root"]

        if "mtime" not in result:
            result["mtime"] = make_mtime_func(src)

        config_root = configuration.get("config_root")
        if config_root and src.startswith(config_root):
            src = "{{config_root}}/{0}".format(src[len(config_root) + 1:])

        if "images" in result and "__images_from__" in result["images"]:
            images_from_path = result["images"]["__images_from__"]

            if isinstance(images_from_path, six.string_types):
                images_from_path = [images_from_path]

            for ifp in images_from_path:

                if not ifp.startswith("/"):
                    ifp = os.path.join(os.path.dirname(src), ifp)

                if not os.path.exists(ifp) or not os.path.isdir(ifp):
                    raise self.BadConfigurationErrorKls(
                          "Specified folder for other configuration files points to a folder that doesn't exist"
                        , path="images.__images_from__"
                        , value=ifp
                        )

                for root, dirs, files in os.walk(ifp):
                    for fle in files:
                        location = os.path.join(root, fle)
                        if fle.endswith(".yml") or fle.endswith(".yaml"):
                            collect_another_source(location
                                , prefix = ["images", os.path.splitext(os.path.basename(fle))[0]]
                                , extra = {"mtime": make_mtime_func(location)}
                                )

            del result["images"]["__images_from__"]

        configuration.update(result, source=src)

        if "harpoon" in result:
            if "extra_files" in result["harpoon"]:
                spec = sb.listof(sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter))
                config_root = {"config_root": result.get("config_root", configuration.get("config_root"))}
                meta = Meta(MergedOptions.using(result, config_root), []).at("harpoon").at("extra_files")
                for extra in spec.normalise(meta, result["harpoon"]["extra_files"]):
                    if os.path.abspath(extra) not in done:
                        if not os.path.exists(extra):
                            raise BadConfiguration("Specified extra file doesn't exist", extra=extra, source=src)
                        collect_another_source(extra)

    def extra_configuration_collection(self, configuration):
        """
        Hook to do any extra configuration collection or converter registration
        """
        harpoon_spec = HarpoonSpec()

        for image in configuration.get('images', {}).keys():
            self.make_image_converters(image, configuration, harpoon_spec)

        self.register_converters(
              { (0, ("content", )): sb.dictof(sb.string_spec(), sb.string_spec())
              , (0, ("harpoon", )): harpoon_spec.harpoon_spec
              , (0, ("authentication", )): harpoon_spec.authentications_spec
              }
            , Meta, configuration, sb.NotSpecified
            )

        # Some other code works better when harpoon no existy
        if configuration["harpoon"] is sb.NotSpecified:
            del configuration["harpoon"]

    def make_image_converters(self, image, configuration, harpoon_spec):
        """Make converters for this image and add them to the configuration"""
        def convert_image(path, val):
            log.info("Converting %s", path)
            everything = path.configuration.root().wrapped()
            meta = Meta(everything, [])
            configuration.converters.started(path)

            base = path.configuration.root().wrapped()
            base.update(configuration.as_dict(ignore=["images"]))
            base.update(val.as_dict(ignore=["images"]))

            base["__image__"] = base
            everything["__image__"] = base

            base["harpoon"] = configuration["harpoon"]
            base["configuration"] = configuration
            return harpoon_spec.image_spec.normalise(meta.at("images").at(image), base)

        converter = Converter(convert=convert_image, convert_path=["images", image])
        configuration.add_converter(converter)

        def convert_tasks(path, val):
            spec = harpoon_spec.tasks_spec(available_actions)
            meta = Meta(path.configuration.root(), []).at("images").at(image).at("tasks")
            configuration.converters.started(path)
            tasks = spec.normalise(meta, val)
            for task in tasks.values():
                task.image = image
            return tasks

        converter = Converter(convert=convert_tasks, convert_path=["images", image, "tasks"])
        configuration.add_converter(converter)
