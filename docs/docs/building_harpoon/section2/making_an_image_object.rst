.. _bh_s2_making_an_image_object:

S2: Making an Image Object
==========================

Let's create an object to represent Image specific options. We're gonna do it
a bit manually in this module and then spend the next two modules introducing
``option_merge`` and ``input_algorithms`` to make it a bit easier and safer to
do.

First, let's make a new folder and make it a python module::

    $ mkdir harpoon/option_spec/
    $ touch harpoon/option_spec/__init__.py

Now let's add a file in ``harpoon/option_spec/image_objs.py``:

.. code-block:: python

    class Image(object):
        def __init__(self, tag, commands):
            self.tag = tag
            self.commands = commands

Before we continue, let's first clarify the meaning. **This is not a test file!!**.

``spec`` here refers to ``specification`` and will make more sense as a
``specification`` when you get introduced to ``input_algorithms``.

Now let's fire up a python interpreter and play with this class::

    $ python
    > from harpoon.option_spec.image_objs import Image
    > image = Image(1, 2)
    > image.tag
    1
    > image.commands
    2

Here we see that the first argument maps to ``image.tag`` and the
second maps to ``image.commands``.

Let's instantiate it a different way::

    $ python
    > from harpoon.option_spec.image_objs import Image
    > image = Image(tag=3, commands=4)
    > image.tag
    3
    > image.commands
    4

This time we passed in ``tag`` and ``commands`` as keyword arguments.

What if we already have a dictionary of arguments?::

    $ python
    > from harpoon.option_spec.image_objs import Image
    > arguments = {"tags": 5, "commands": 6}
    > image = Image(**arguments)
    > image.tag
    5
    > image.commands
    6

I hope you see where I'm going with this:

.. code-block:: python

    from harpoon.option_spec.image_objs import Image

    class Collector(App):
        def start(self, cli_args):
            self.configuration["image"] = Image(**self.configuration)
            available_tasks[cli_args['harpoon']['task']](self, cli_args)

And now in our ``build_and_run`` task:

.. code-block:: python

    @a_task
    def build_and_run(collector, cli_args):
        tag = collector.configuration["image"].tag
        dockerfile_commands = collector.configuration["image"].commands

        [..]

Doing it this way without any sort of type/error checking is a bit reckless and
unsafe. The good news is ``option_merge`` and ``input_algorithms`` improve the
situation quite a bit :)

Methods!!
---------

In the meantime, now that we have an Image object, we can have methods on the
Image that do the work for us.

Change ``build_and_run``:

.. code-block:: python

    @a_task
    def build_and_run(collector, cli_args):
        image = collector.configuration['image']
        harpoon = cli_args["harpoon"]

        image.build(harpoon)
        image.run(harpoon)

And let's add those methods to our Image:

.. code-block:: python

    class Image(object):
        def __init__(self, tag, commands):
            self.tag = tag
            self.commands = commands

        def dockerfile(self):
            """Get us a file representing the commands in our dockerfile"""
            dockerfile = tempfile.NamedTemporaryFile(delete=True)
            dockerfile.write("\n".join(self.commands))
            dockerfile.flush()
            dockerfile.seek(0)
            return dockerfile

        def build(self, harpoon):
            """Build a docker image"""
            client = harpoon["make_client"]()
            log.info("Building an image: %s", self.tag)

            try:
                for line in client.build(fileobj=self.dockerfile(), rm=True, tag=self.tag, pull=False):
                    print(line)
            except docker.errors.APIError as error:
                raise BadImage("Failed to build the image", tag=self.tag, error=error)

        def run(self, harpoon):
            """Run our docker container"""
            client = harpoon["make_client"]()
            log.info("Making a container from an image (%s)", self.tag)

            try:
                container = client.create_container(image=self.tag)
            except docker.errors.APIError as error:
                raise BadImage("Failed to create the container", image=self.tag, error=error)

            log.info("Starting a container: %s", container["Id"])
            try:
                dockerpty.start(harpoon["make_client"](), container)
            except docker.errors.APIError as error:
                raise BadContainer("Failed to start the container", container=container["Id"], image=self.tag, error=error)

            log.info("Cleaning up a container: %s", container["Id"])
            try:
                client.remove_container(container)
            except docker.errors.APIError as error:
                log.error("Failed to remove the container :(\tcontainer=%s\terror=%s", container["Id"], error)

There we go, now our task is much smaller and the actual logic is out of
``actions.py``, which is important for scaling ``actions.py`` to all the default
tasks that Harpoon has.

A note about self
-----------------

For those unfamiliar with Python, the ``self`` convention may confuse you
initially. If that's the case, do read on!

In Python, we have functions and methods:

.. code-block:: python

    def a_function(one, two):
        print(one, two)

    class AClass(object);
        def a_method(self, one, two):
            print(self, one, two)

    a_function(1, 2) # will print (1, 2)

    AClass().a_method(1, 2) # will print ((<__main__.AClass object at 0x10746fed0>, 1, 2))

What happens here is the method is ``bound`` to the instance it's called from.
So when it gets called the instance gets automatically passed in as the first
argument. This first argument can be named anything you want, but
conventionally it's named ``self``.

