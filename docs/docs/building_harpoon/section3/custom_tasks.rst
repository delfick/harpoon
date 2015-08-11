.. _bh_s3_custom_tasks:

S3: Custom Tasks
================

First, let's create an object to represent tasks:

``option_spec/task_objs.py``:

    .. code-block:: python

        from input_algorithms.dictobj import dictobj

        class Task(dictobj):
            fields = ["action", ("description", ""), ("label", "Harpoon")]

            def run(self, collector, image, available_actions, tasks=None):
                available_actions[self.action](collector, image, tasks)

Eagle eyed viewers may notice that the signature for our ``actions`` in
``actions.py`` is actually (collector, cli_args) and not this
(collector, image, tasks) I'm passing in.

You may remember that we put cli_args inside the configuration in the
``extra_prepare`` step, so passing it around is no longer that necessary and we
need to tell the action what image to access. So let's change everything to use
this new object and signature:

``collector.py``

    .. code-block:: python

        from harpoon.option_spec.task_objs import Task
        from harpoon.actions import available_actions

        class Collector(Collector):
            [..]

            def start(self):
                tasks = {name: Task(name) for name in available_actions}
                chosen_task = self.configuration["harpoon"]["task"]
                chosen_image = self.configuration["harpoon"]["image"]
                tasks[chosen_task].run(self, chosen_image, available_actions, tasks)

``actions.py``

    .. code-block:: python

        [..]

        @an_action
        def list_tasks(collector, image, tasks):
            """Tasks themselves don't get introduced till section3, so let's just list the actions"""
            [..]

        @an_action
        def build_and_run(collector, image, tasks):
            [..]

            harpoon = collector.configuration["harpoon"]
            image.build(harpoon)
            image.run(harpoon)

Oh, look at that! Don't even need cli_args anyways!

So, let's improve on this a bit by making an object just for finding tasks:

``errors.py``

    .. code-block:: python

        [..]

        class BadTask(DelfickError):
            desc = "Something wrong with the task"

``task_finder.py``

    .. code-block:: python

        from harpoon.option_spec.task_objs import Task
        from harpoon.actions import available_actions
        from harpoon.errors import BadTask

        class TaskFinder(object):
            def __init__(self, collector):
                self.tasks = {}
                self.collector = collector

            def task_runner(self, task, **kwargs):
                if task not in self.tasks:
                    raise BadTask("Unknown task", task=task, available=sorted(list(self.tasks.keys())))

                image = self.collector.configuration['harpoon']['image']
                return self.tasks[task].run(self.collector, image, available_actions, self.tasks, **kwargs)

            def default_tasks(self):
                return dict((name, Task(action=name, label="Harpoon")) for name in available_actions)

            def find_tasks(self):
                self.tasks.update(self.default_tasks())

``collector.py``

    .. code-block:: python

        from harpoon.task_finder import TaskFinder

        class Collector(Collector):
            [..]

            def start(self):
                task_finder = TaskFinder(self)
                task_finder.find_tasks()
                task_finder.task_runner(self.configuration["harpoon"]["task"])

In the real Harpoon we don't have a ``start`` method on Collector and instead
choose to put the ``task_runner`` function in the configuration and use it from
``executor.py`` like so:

``collector.py``

    .. code-block:: python

        class Collector(Collector):

            [..]

            # Instead of the start function
            def extra_prepare_after_activation(self, configuration, cli_args):
                """Called after the configuration.converters are activated"""
                task_finder = TaskFinder(self)
                configuration["task_runner"] = task_finder.task_runner
                task_finder.find_tasks()

``executor.py``

    .. code-block:: python

        class Harpoon(App):

            [..]

            def execute(self, args, extra_args, cli_args, logging_handler):
                cli_args['harpoon']['make_client'] = make_client

                collector = Collector()
                collector.prepare(args.config.name, cli_args)
                collector.configuration["task_runner"](collector.configuration["harpoon"]["task"])

Whilst we're at it, let's update our list_tasks action to take into account
description and label:

``actions.py``

    .. code-block:: python

        from textwrap import dedent
        import itertools

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

And update the build_and_run task to use the image that is passed in:

``actions.py``

    .. code-block:: python

        @an_action
        def build_and_run(collector, image, tasks):
            if not image:
                raise BadImage("Please specify an image to work with!")
            if image not in collector.configuration["images"]:
                raise BadImage("No such image", wanted=image, available=list(collector.configuration["images"].keys()))
            image = collector.configuration["images"][image]

            harpoon = collector.configuration["harpoon"]
            image.build(harpoon)
            image.run(harpoon)

Getting tasks from configuration
--------------------------------

We're now gonna make a spec for tasks and then use it to normalise the
configuration and get tasks defined from there.

``option_spec/task_objs.py``

    .. code-block:: python

        from input_algorithms import spec_base as sb

        class Task(dictobj):
            [..]

        tasks_spec = sb.dictof(
              sb.string_spec()
            , sb.create_spec(Task
                , action = sb.string_spec()
                , description = sb.string_spec()
                , label = sb.defaulted(sb.string_spec(), "Project")
                )
            )

Now let's use it:

``collector.py``

    .. code-block:: python

        from harpoon.option_spec.task_objs import tasks_spec

        class Collector(Collector):
            [..]

            def install_image_converters(self, configuration, image):
                def convert_image(path, val):
                    [..]

                converter = converter(convert=convert_image, convert_path=["images", image])
                configuration.add_converter(converter)

                def convert_tasks(path, val):
                    log.info("converting %s", path)
                    everything = path.configuration.root().wrapped()
                    meta = Meta(everything, [("images", ""), (image, ""), ("tasks", "")])
                    configuration.converters.started(path)
                    return tasks_spec.normalise(meta, val)

                converter = Converter(convert=convert_tasks, convert_path=["images", image, "tasks"])
                configuration.add_converter(converter)

Now we are guaranteed that the value at ``configuration["images"][image]["tasks"]``
is a dictionary of strings to Task objects.

So let's use this dictionary:

``task_finder.py``

    .. code-block:: python

        class TaskFinder(object):
            [..]

            def find_tasks(self):
                self.tasks.update(self.default_tasks())

                configuration = self.collector.configuration
                for image in configuration["images"]:
                    if ["images", image, "tasks"] in configuration:
                        self.tasks.update(configuration[["images", image, "tasks"]])

.. note:: We don't do collector.configuration["images"][image] at any point here
 otherwise we'll be converting configuration["images"][image] for all the images
 just to find all the tasks and we don't want to do that.

And done!

Making it better
----------------

We can improve upon this in two awesome ways:

#. Validate the action against the ``available_actions``

#. Associate each custom task with the image it was defined with so that you
   don't have to repeat yourself when calling the task.

The first one involves changing the ``tasks_spec``. Let's make it a function
that takes in the available actions and then complain if the provided action
is not one of those:

.. code-block:: python

    tasks_spec = lambda available_actions: sb.dictof(
          sb.stringt_spec()
        , sb.create_spec(Task
            , action = sb.string_choice_spec(available_actions, "No such action")
            , description = sb.string_spec()
            , label = sb.defaulted(sb.string_spec(), "Project")
            )
        )

Let's also make it so that it defaults to the "build_and_run" task as this is
the most likely task someone will want to use:

.. code-block:: python

    tasks_spec = lambda available_actions: sb.dictof(
          sb.stringt_spec()
        , sb.create_spec(Task
            , action = sb.defaulted(sb.string_choice_spec(available_actions, "No such action"), "build_and_run")
            , description = sb.string_spec()
            , label = sb.defaulted(sb.string_spec(), "Project")
            )
        )

That was easy!

Now we want to make it so that when we choose that task, it uses the image the
task was defined on:

``collector.py``:

    .. code-block:: python

        from harpoon.actions import available_actions

        class Collector(Collector):
            [..]

            def install_image_converters(self, configuration, image):
                [..]

                def convert_tasks(path, val):
                    log.info("converting %s", path)
                    everything = path.configuration.root().wrapped()
                    meta = meta(everything, [("images", ""), (image, ""), ("tasks", "")])
                    configuration.converters.started(path)
                    tasks = tasks_spec(available_actions).normalise(meta, val)

                    # Set an image attribute on each task with this image
                    for task in tasks.values():
                        task.image = image

                    return tasks

                [..]

``task_finder.py``:

    .. code-block:: python

        class TaskFinder(object):
            [..]

            def task_runner(self, task, **kwargs):
                if task not in self.tasks:
                    raise BadTask("Unknown task", task=task, available=sorted(list(self.tasks.keys())))

                image = getattr(self.tasks[task], "image", self.collector.configuration['harpoon']['image'])
                return self.tasks[task].run(self.collector, image, available_actions, self.tasks, **kwargs)

.. note:: ``getattr`` is a function that has a signature of (obj, attr, default)
  and will get the ``attr`` attribute on ``obj`` or if no such attribute exists
  it will return ``default``. So what we're doing here is getting the ``image``
  attribute off the task, or if there is no ``image`` attribute, just using
  the image that was provided via the commandline.

And congratulations, you just implemented custom tasks!

Well, you can't really customize much in your custom tasks, but that's easily
fixed.

``option_spec/image_objs.py``:

    .. code-block:: python

        from input_algorithms.dictobj import dictobj

        class Image(dictobj):
            # Instead of an __init__ method
            fields = ["tag", "command", "commands"]

            [..]

        image_spec = sb.create_spec(Image
            , tag = sb.string_spec()
            , command = sb.defaulted(sb.string_spec(), None)
            , commands = sb.listof(sb.string_spec())
            )

Now we have a ``command`` field to our Image object which we can override in our
custom task. Now we just have to actually use it:

``option_spec/image_objs.py``:

    .. code-block:: python

        class Image(dictobj):
            [..]

            def run(self, harpoon):
                [..]

                try:
                    container = client.create_container(image=self.tag, command=self.command)
                except docker.errors.APIError as error:
                    raise BadImage("Failed to create the container", image=self.tag, error=error)

                [..]

Excellent, now let's change our config.yml:

.. code-block:: yaml

    ---

    images:
        mine:
            tag: local/lolz

            commands:
                - FROM gliderlabs/alpine:3.1
                - RUN apk-install figlet --update-cache --repository http://dl-3.alpinelinux.org/alpine/edge/testing/
                - CMD figlet lolz

            tasks:
                hello:
                    description: Say hello
                    options:
                        command: figlet hello

And make our tasks object understand this new ``options`` configuration we want
to use:

``option_spec/task_objs``

    .. code-block:: python

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

        tasks_spec = lambda available_actions: sb.dictof(Task
              sb.string_spec()
            , sb.create_spec(Task
                ...
                , options = sb.dictionary_spec()
                ...
                )
            )

So what we've done here is update the configuration to have the new options
from the task, and because we haven't converted the image yet, it will take in
these new options when it finally does.

And now run ``harpoon hello``.

