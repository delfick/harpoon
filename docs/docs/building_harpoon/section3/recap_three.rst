.. _bh_s3_recap_three:

Recap Three
===========

Congratulations! Your harpoon now deals with context, image inheritance, custom
tasks and the ability to format parts of the configuration with itself.

``config.yml``

    .. code-block:: yaml

        ---

        tag_prefix: local

        images:
            cloc-base:
                context: false

                tag: "{tag_prefix}/{_key_name_1}"

                commands:
                    - FROM ubuntu:14.04
                    - RUN sudo apt-get update && apt-get install -y cloc

            cloc:
                context:
                    parent_dir: "{config_root}/harpoon"

                tag: "{tag_prefix}/{_key_name_1}"

                commands:
                    - [FROM, "{images.cloc-base}"]
                    - ADD . /project
                    - CMD cloc /project

            mine:
                context: false

                tag: "{tag_prefix}/{_key_name_1}"

                commands:
                    - FROM gliderlabs/alpine:3.1
                    - RUN apk-install figlet --update-cache --repository http://dl-3.alpinelinux.org/alpine/edge/testing/
                    - CMD figlet lolz

                tasks:
                    hello:
                        description: Say hello
                        options:
                            command: figlet hello

                    config_root:
                        description: say the config root
                        options:
                            command: "figlet {config_root}"

``setup.py``

    .. code-block:: python

        from setuptools import setup, find_packages

        setup(
              name = "my-harpoon"
            , version = 0.1
            , packages = ['harpoon'] + ['harpoon.%s' % pkg for pkg in find_packages('harpoon')]

            , install_requires =
              [ "delfick_app==0.6.7"
              , "docker-py==1.2.2"
              , "dockerpty==0.3.4"
              , "pyYaml==3.11"
              , "requests[security]"
              , "input_algorithms==0.4.4.6"
              , "option_merge==0.9.8.2"
              ]

            , entry_points =
              { 'console_scripts' :
                [ 'harpoon = harpoon.executor:main'
                ]
              }
            )

``harpoon/__init__.py``

``harpoon/actions.py``

    .. code-block:: python

        from harpoon.errors import BadImage
        from harpoon.layers import Layers

        from textwrap import dedent
        import itertools

        available_actions = {}

        def an_action(func):
            available_actions[func.__name__] = func
            return func

        @an_action
        def list_tasks(collector, image, tasks):
            """List the available_tasks"""
            print("Available tasks to choose from are:")
            print("Use the --task option to choose one")
            print("")
            keygetter = lambda item: item[1].label
            tasks = sorted(tasks.items(), key=keygetter)
            for label, items in itertools.groupby(tasks, keygetter):
                print("--- {0}".format(label))
                print("----{0}".format("-" * len(label)))
                sorted_tasks = sorted(list(items), key=lambda item: len(item[0]))
                max_length = max(len(name) for name, _ in sorted_tasks)
                for key, task in sorted_tasks:
                    desc = dedent(task.description or "").strip().split('\n')[0]
                    print("\t{0}{1} :-: {2}".format(" " * (max_length-len(key)), key, desc))
                print("")

        @an_action
        def build_and_run(collector, image, tasks):
            if not image:
                raise BadImage("Please specify an image to work with!")
            if image not in collector.configuration["images"]:
                raise BadImage("No such image", wanted=image, available=list(collector.configuration["images"].keys()))
            image = collector.configuration["images"][image]

            harpoon = collector.configuration["harpoon"]
            image.build(harpoon, collector.configuration["images"])
            image.run(harpoon)

        @an_action
        def build(collector, image, tasks):
            if not image:
                raise BadImage("Please specify an image to work with!")
            if image not in collector.configuration["images"]:
                raise BadImage("No such image", wanted=image, available=list(collector.configuration["images"].keys()))
            image = collector.configuration["images"][image]

            harpoon = collector.configuration["harpoon"]
            image.build(harpoon, collector.configuration["images"])

        @an_action
        def show(collector, image, tasks):
            layers = Layers(collector.configuration["images"])
            layers.add_all_to_layers()
            for index, layer in enumerate(layers.layered):
                print("Layer {0}".format(index+1))
                for _, image in layer:
                    print("\t{0}".format(image.name))
                print("")

``harpoon/collector.py``

    .. code-block:: python

        from harpoon.option_spec.image_objs import image_spec
        from harpoon.option_spec.task_objs import tasks_spec
        from harpoon.actions import available_actions
        from harpoon.errors import BadConfiguration
        from harpoon.task_finder import TaskFinder

        from option_merge.converter import Converter
        from option_merge.collector import Collector
        from option_merge import MergedOptions
        from input_algorithms.meta import Meta
        import logging
        import yaml

        log = logging.getLogger("harpoon.collector")

        class Collector(Collector):
            BadConfigurationErrorKls = BadConfiguration

            def find_missing_config(self, configuration):
                if "images" not in self.configuration:
                    raise self.BadConfigurationErrorKls("Didn't find any images in the configuration")
                if not isinstance(configuration["images"], dict):
                    raise self.BadConfigurationErrorKls("images needs to be a dictionary!", got=type(configuration["images"]))

            def read_file(self, location):
                return yaml.load(open(location))

            def start_configuration(self):
                return MergedOptions()

            def add_configuration(self, configuration, collect_another_source, done, result, src):
                configuration.update(result)

            def extra_prepare(self, configuration, cli_args):
                configuration.update(
                    { "harpoon": cli_args["harpoon"]
                    , "cli_args": cli_args
                    }
                  )

            def extra_configuration_collection(self, configuration):
                for image in configuration["images"]:
                    self.install_image_converters(configuration, image)

            def install_image_converters(self, configuration, image):
                def convert_image(path, val):
                    log.info("Converting %s", path)
                    everything = path.configuration.root().wrapped()
                    meta = Meta(everything, [("images", ""), (image, "")])
                    configuration.converters.started(path)
                    return image_spec.normalise(meta, val)

                converter = Converter(convert=convert_image, convert_path=["images", image])
                configuration.add_converter(converter)

                def convert_tasks(path, val):
                    log.info("converting %s", path)
                    everything = path.configuration.root().wrapped()
                    meta = Meta(everything, [("images", ""), (image, ""), ("tasks", "")])
                    configuration.converters.started(path)
                    tasks = tasks_spec(available_actions).normalise(meta, val)

                    for task in tasks.values():
                        task.image = image

                    return tasks

                converter = Converter(convert=convert_tasks, convert_path=["images", image, "tasks"])
                configuration.add_converter(converter)

            def extra_prepare_after_activation(self, configuration, cli_args):
                task_finder = TaskFinder(self)
                configuration["task_runner"] = task_finder.task_runner
                task_finder.find_tasks()

``harpoon/errors.py``

    .. code-block:: python

        from delfick_error import DelfickError

        class BadTask(DelfickError):
            desc = "Something wrong with the task"
        class BadImage(DelfickError):
            desc = "Something bad about the image"
        class BadOption(DelfickError):
            desc = "Bad option"
        class BadContainer(DelfickError):
            desc = "Something bad about the container"
        class ImageDepCycle(DelfickError):
            desc = "Found a circular dependency"
        class BadOptionFormat(DelfickError):
            desc = "Something bad with our option format"
        class BadConfiguration(DelfickError):
            desc = "Something wrong with the configuration"

``harpoon/executor.py``

    .. code-block:: python

        from harpoon.collector import Collector

        from delfick_app import App
        import argparse
        import logging
        import docker

        class Harpoon(App):
            cli_categories = ['harpoon']
            cli_positional_replacements = [('--task', 'list_tasks'), "--image"]

            def execute(self, args, extra_args, cli_args, logging_handler):
                cli_args['harpoon']['make_client'] = make_client

                collector = Collector()
                collector.prepare(args.config.name, cli_args)
                collector.configuration["task_runner"](collector.configuration["harpoon"]["task"])

            def specify_other_args(self, parser, defaults):
                parser.add_argument("--config"
                    , help = "Location of the configuration"
                    , type = argparse.FileType('r')
                    , default = "./config.yml"
                    )

                parser.add_argument('--task'
                    , help = 'The task to run'
                    , dest = 'harpoon_task'
                    , **defaults['--task']
                    )

                parser.add_argument("--image"
                    , help = "the image to work with"
                    , dest = "harpoon_image"
                    , **defaults["--image"]
                    )

            def setup_other_logging(self, args, verbose=False, silent=False, debug=False):
                logging.getLogger("requests").setLevel([logging.CRITICAL, logging.ERROR][verbose or debug])

        def make_client():
            """Make a docker context"""
            return docker.Client(**docker.utils.kwargs_from_env(assert_hostname=False))

        main = Harpoon.main
        if __name__ == "__main__":
            main()

``harpoon/formatter.py``

    .. code-block:: python

        from harpoon.errors import BadOptionFormat

        from option_merge.formatter import MergedOptionStringFormatter
        from input_algorithms.meta import Meta

        class MergedOptionStringFormatter(MergedOptionStringFormatter):
            def get_string(self, key):
                """Get a string from all_options"""
                if key not in self.all_options:
                    kwargs = {}
                    if len(self.chain) > 1:
                        kwargs['source'] = Meta(self.all_options, self.chain[-2]).source
                    raise BadOptionFormat("Can't find key in options", key=key, chain=self.chain, **kwargs)

                return super(MergedOptionStringFormatter, self).get_string(key)

            def special_get_field(self, value, args, kwargs, format_spec=None):
                """Also take the spec into account"""
                if format_spec in ("env", ):
                    return value, ()

                if value in self.chain:
                    raise BadOptionFormat("Recursive option", chain=self.chain + [value])

            def special_format_field(self, obj, format_spec):
                """Know about any special formats"""
                if format_spec == "env":
                    return "${{{0}}}".format(obj)

``harpoon/helpers.py``

    .. code-block:: python

        from contextlib import contextmanager
        import tempfile
        import os

        @contextmanager
        def a_temp_file():
            """Yield the name of a temporary file and ensure it's removed after use"""
            filename = None
            try:
                tmpfile = tempfile.NamedTemporaryFile(delete=False)
                filename = tmpfile.name
                yield tmpfile
            finally:
                if filename and os.path.exists(filename):
                    os.remove(filename)

``harpoon/layers.py``

    .. code-block:: python

        from harpoon.errors import ImageDepCycle

        class Layers(object):
            """
            Used to order the creation of many images.

            Usage::

                layers = Layers({"image1": image1, "image2": "image2, "image3": image3, "image4": image4})
                layers.add_to_layers("image3")
                for layer in layers.layered:
                    # might get something like
                    # [("image3", image4), ("image2", image2)]
                    # [("image3", image3)]

            When we create the layers, it will do a depth first addition of all dependencies
            and only add a image to a layer that occurs after all it's dependencies.

            Cyclic dependencies will be complained about.
            """
            def __init__(self, images, all_images=None):
                self.images = images
                self.all_images = all_images
                if self.all_images is None:
                    self.all_images = images

                self.accounted = {}
                self._layered = []

            def reset(self):
                """Make a clean slate (initialize layered and accounted on the instance)"""
                self.accounted = {}
                self._layered = []

            @property
            def layered(self):
                """Yield list of [[(name, image), ...], [(name, image), ...], ...]"""
                result = []
                for layer in self._layered:
                    nxt = []
                    for name in layer:
                        nxt.append((name, self.all_images[name]))
                    result.append(nxt)
                return result

            def add_all_to_layers(self):
                """Add all the images to layered"""
                for image in sorted(self.images):
                    self.add_to_layers(image)

            def add_to_layers(self, name, chain=None):
                layered = self._layered

                if name not in self.accounted:
                    self.accounted[name] = True
                else:
                    return

                if chain is None:
                    chain = []
                chain = chain + [name]

                for dependency in sorted(self.all_images[name].dependencies(self.all_images)):
                    dep_chain = list(chain)
                    if dependency in chain:
                        dep_chain.append(dependency)
                        raise ImageDepCycle(chain=dep_chain)
                    self.add_to_layers(dependency, dep_chain)

                layer = 0
                for dependency in self.all_images[name].dependencies(self.all_images):
                    for index, deps in enumerate(layered):
                        if dependency in deps:
                            if layer <= index:
                                layer = index + 1
                            continue

                if len(layered) == layer:
                    layered.append([])
                layered[layer].append(name)

``harpoon/task_finder.py``

    .. code-block:: python

        from harpoon.actions import available_actions
        from harpoon.option_spec.task_objs import Task
        from harpoon.errors import BadTask

        class TaskFinder(object):
            def __init__(self, collector):
                self.tasks = {}
                self.collector = collector

            def task_runner(self, task, **kwargs):
                if task not in self.tasks:
                    raise BadTask("Unknown task", task=task, available=sorted(list(self.tasks.keys())))

                image = getattr(self.tasks[task], "image", self.collector.configuration['harpoon']['image'])
                return self.tasks[task].run(self.collector, image, available_actions, self.tasks, **kwargs)

            def default_tasks(self):
                return dict((name, Task(action=name, label="Harpoon")) for name in available_actions)

            def find_tasks(self):
                self.tasks.update(self.default_tasks())

                configuration = self.collector.configuration
                for image in configuration["images"]:
                    if ["images", image, "tasks"] in configuration:
                        self.tasks.update(configuration[["images", image, "tasks"]])

``harpoon/option_spec/__init__.py``

``harpoon/option_spec/image_objs.py``

    .. code-block:: python

        from harpoon.option_spec.command_objs import commands_spec
        from harpoon.formatter import MergedOptionStringFormatter
        from harpoon.errors import BadImage, BadContainer
        from harpoon.ship.context import ContextBuilder
        from harpoon import helpers as hp

        from input_algorithms import spec_base as sb
        from input_algorithms.dictobj import dictobj
        from contextlib import contextmanager
        import dockerpty
        import logging
        import docker
        import os

        log = logging.getLogger("harpoon.option_spec.image_objs")

        class Context(dictobj):
            fields = ["enabled", "parent_dir"]

        class Image(dictobj):
            fields = ["name", "tag", "context", "command", "commands"]

            @contextmanager
            def dockerfile(self):
                with hp.a_temp_file() as fle:
                    fle.write(self.commands.lines)
                    fle.flush()
                    fle.seek(0)
                    os.utime(fle.name, (0, 0))
                    yield fle

            def dependencies(self, images):
                parent_image = self.commands.parent_image
                if isinstance(parent_image, Image):
                    yield parent_image.name

            @contextmanager
            def the_context(self):
                with ContextBuilder().make_context(self.context) as context:
                    with self.dockerfile() as dockerfile:
                        context.tarfile.add(dockerfile.name, "./Dockerfile")
                    yield context

            def build(self, harpoon, images):
                for dependency in self.dependencies():
                    images[dependency].build(harpoon, images)

                client = harpoon["make_client"]()
                log.info("Building an image: %s", self.tag)

                try:
                    with self.the_context() as context:
                        context.close()
                        for line in client.build(fileobj=context.fileobj, custom_context=True, rm=True, tag=self.tag, pull=False):
                            print(line)
                except docker.errors.APIError as error:
                    raise BadImage("Failed to build the image", tag=self.tag, error=error)

            def run(self, harpoon):
                client = harpoon["make_client"]()
                log.info("Making a container from an image (%s)", self.tag)
                try:
                    container = client.create_container(image=self.tag, command=self.command)
                except docker.errors.APIError as error:
                    raise BadImage("Failed to create the container", image=self.tag, error=error)

                log.info("Starting a container: %s", container["Id"])
                try:
                    dockerpty.start(harpoon['make_client'](), container)
                except docker.errors.APIError as error:
                    raise BadContainer("Failed to start the container", container=container["Id"], image=self.tag, error=error)

                log.info("Cleaning up a container: %s", container["Id"])
                try:
                    client.remove_container(container)
                except docker.errors.APIError as error:
                    log.error("Failed to remove the container :(\tcontainer=%s\terror=%s", container["Id"], error)

        def context_spec():
            """Spec for specifying context options"""
            return sb.dict_from_bool_spec(lambda meta, val: {"enabled": val}
                , sb.create_spec(Context
                    , enabled = sb.defaulted(sb.boolean(), True)
                    , parent_dir = sb.directory_spec(sb.formatted(sb.defaulted(sb.string_spec(), "{config_root}"), formatter=MergedOptionStringFormatter))
                    )
                )

        formatted_string = sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)

        image_spec = sb.create_spec(Image
            , tag = formatted_string
            , name = sb.formatted(sb.overridden("{_key_name_1}"), formatter=MergedOptionStringFormatter)
            , context = context_spec()
            , command = sb.defaulted(formatted_string, None)
            , commands = commands_spec()
            )

``harpoon/option_spec/task_objs.py``

    .. code-block:: python

        from input_algorithms.dictobj import dictobj
        from input_algorithms import spec_base as sb

        class Task(dictobj):
            fields = ["action", ("options", None), ("description", ""), ("label", "Harpoon")]

            def run(self, collector, image, available_actions, tasks=None):
                if self.options is None:
                    options = {}
                elif hasattr(self.options, "as_dict"):
                    options = self.options.as_dict()

                if image:
                    collector.configuration.update({"images": {image: options}})
                available_actions[self.action](collector, image, tasks)

        tasks_spec = lambda available_actions: sb.dictof(
              sb.string_spec()
            , sb.create_spec(Task
                , action = sb.defaulted(sb.string_choice_spec(available_actions, "No such action"), "build_and_run")
                , options = sb.dictionary_spec()
                , description = sb.string_spec()
                , label = sb.defaulted(sb.string_spec(), "Project")
                )
            )

``harpoon/ship/__init__.py``

``harpoon/ship/context.py``

    .. code-block:: python

        from harpoon import helpers as hp

        from contextlib import contextmanager
        import tarfile
        import os

        class ContextWrapper(object):
            def __init__(self, tarfile, fileobj):
                self.tarfile = tarfile
                self.fileobj = fileobj

            def close(self):
                self.tarfile.close()
                self.fileobj.flush()
                self.fileobj.seek(0)

        class ContextBuilder(object):
            @contextmanager
            def make_context(self, context):
                with hp.a_temp_file() as f:
                    t = tarfile.open(mode="w:gz", fileobj=f)
                    if context.enabled:
                        for filename, arcname in self.find_files(context.parent_dir):
                            t.add(filename, arcname)
                    yield ContextWrapper(t, f)

            def find_files(self, parent_dir):
                for root, dirs, files in os.walk(parent_dir):
                    for filename in files:
                        location = os.path.join(root, filename)
                        yield location, os.path.relpath(location, parent_dir)

