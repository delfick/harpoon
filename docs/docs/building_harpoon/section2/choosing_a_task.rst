.. _bh_s2_choosing_a_task:

S2: Choosing a task
===================

Harpoon is all about finding and executing tasks, whether they be tasks defined
by harpoon itself, or tasks defined in the configuration.

We're not quite at the point where we can define tasks in the configuration,
but we can setup the Harpoon default tasks.

First, let's get the ``chosen task``, i.e. the task that the user wants to
execute.

in ``executor.py``:

.. code-block:: python

    def specify_other_args(self, parser, defaults):
        parser.add_argument("--config"
            , help = "Location of the configuration"
            , type = argparse.FileType('r')
            , default = "./config.yml"
            )

        parser.add_argument("--task"
            , help = "The task to execute"
            , required = True
            )

Now when we run ``harpoon`` it'll complain that you haven't specified ``--task``.

The next step is to do something with the task:

.. code-block:: python

    def execute(self, args, extra_args, cli_args, logging_handler):
        print(args.task)

Before we continue, we're gonna make use of some features of DelfickApp that we
are currently ignoring.

Firstly, you may have noticed that you can just specify ``task`` as the first
positional argument when you run the real harpoon. This is a custom feature I've
implemented in delfick_app because ``arpgarse`` doesn't allow optional positional
arguments.

The good news is all you have to do is the following:

.. code-block:: python

    class Harpoon(App):
        cli_positional_replacements = ['--task']

        def specify_other_args(self, parser, defaults):
            [..]

            parser.add_argument("--task"
                , help = "The task to execute"
                )

And now you can do something like ``harpoon something`` and ``args.task`` will
equal "something" :)

We can even do defaults:

.. code-block:: python

    class Harpoon(App):
        cli_positional_replacements = [('--task', 'list_tasks')]

        def specify_other_args(self, parser, defaults):
            [..]

            parser.add_argument("--task"
                , help = "The task to execute"
                , **defaults['--task']
                )

That ``defaults`` argument will equal to ``{'--task': {'default': 'list_tasks'}}``
and so doing ``**defaults['--task']`` is the same as saying
``default = 'list_tasks'``.

Now just run ``harpoon``, if you still have that print statement, it should
print out ``list_tasks``.

One last change before we do something useful with this information:

.. code-block:: python

    class Harpoon(App):
        cli_categories = ['harpoon']

        [..]

        def execute(self, args, extra_args, cli_args, logging_handler):
            print(args.harpoon_task)
            print(cli_args["harpoon"]["task"])

        def specify_other_args(self, parser, defaults):
            [..]

            parser.add_argument("--task"
                , help = "The task to execute"
                , dest = "harpoon_task"
                , **defaults['--task']
                )

Here we've namespaced ``task`` by ``harpoon`` by making it go onto ``args`` as
``harpoon_task`` and then because we've defined the ``harpoon`` cli_category,
``cli_args`` has broken out the ``harpoon`` options into a sub dictionary.

This will be more useful to us later on, but we might as well namespace it from
the start.

Making the actions
------------------

Let's make ``harpoon/actions.py``:

.. code-block:: python

    available_actions = {}

    def an_action(func):
        available_actions[func.__name__] = func
        return func

    @an_action
    def list_tasks():
        """Tasks themselves don't get introduced till section3, so let's just list the actions"""
        print('\n'.join("{0}: {1}".format(name, func.__doc__) for name, func in available_actions.items()))

And in ``harpoon/executor.py``:

.. code-block:: python

    from harpoon.actions import available_actions

    class Harpoon(App):
        def execute(self, args, extra_args, cli_args, logging_handler):
            available_actions[cli_args["harpoon"]["task"]]()

Now let's just run ``harpoon``.

Congratulations! Your very first task!

What's a decorator?
-------------------

You may have noticed I introduced some new syntax in ``actions.py`` with the ``@``.

This is called the ``decorator`` syntax and is equivalent to saying:

.. code-block:: python

    def list_tasks():
        """List all the tasks"""
        [..]
    list_tasks = an_action(list_tasks)

In our case, ``an_action`` puts a reference to the task in the ``available_actions``
dictionary and returns the function as is.

Build and run
-------------

So let's create a task that does our build_and_run logic that we used to have
in ``execute``:

.. code-block:: python

    @an_action
    def build_and_run():
        collector = Collector()
        # Oh wait! we need a reference to cli_args here!

Well, we have two problems. Firstly we need reference to data we have in
``executor`` and secondly later on we want to already have collected our
configuration so that we can find any custom tasks defined there.

So instead, we'll do it the other way round and make the ``Collector`` find
and execute the task.

So, in ``executor.py`` return it to:

.. code-block:: python

    def execute(self, args, extra_args, cli_args, logging_handler):
        cli_args['harpoon']['make_client'] = make_client

        collector = Collector()
        collector.prepare(args.config)
        collector.start(cli_args)

Note two changes here. Firstly we're adding our ``make_client`` helper to the
``harpoon`` namespace in ``cli_args`` and we're passing all of ``cli_args`` into
``Collector.start``.

and then in ``collector.py``:

.. code-block:: python

    from harpoon.tasks import available_actions

    class Collector(object):
        [..]

        def start(self, cli_args):
            available_actions[cli_args['harpoon']['task']](self, cli_args)

So now our start method finds the task and calls it with itself and the cli_args.
Hence we must change the signature of our list_tasks task:

.. code-block:: python

    @an_action
    def list_tasks(collector, cli_args):
        [..]

Now, we can add a build_and_run task!

.. code-block:: python

    import tempfile
    import logging
    import docker
    import dockerpty

    [..]

    log = logging.getLogger("harpoon.actions")

    @an_action
    def build_and_run(collector, cli_args):
        tag = collector.configuration["tag"]
        dockerfile_commands = collector.configuration["commands"]

        client = cli_args['harpoon']['make_client']()

        dockerfile = tempfile.NamedTemporaryFile(delete=True)
        dockerfile.write("\n".join(dockerfile_commands))
        dockerfile.flush()
        dockerfile.seek(0)

        log.info("Building an image: %s", tag)
        try:
            for line in client.build(fileobj=dockerfile, rm=True, tag=tag):
                print(line)
        except docker.errors.APIError as error:
            raise BadImage("Failed to build the image", tag=tag, error=error)

        [..]

