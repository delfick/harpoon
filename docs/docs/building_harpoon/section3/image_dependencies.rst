.. _bh_s3_image_dependencies:

S3: Image dependencies
======================

It's all fine and good being able to define multiple images, but it's really
useful if we can then connect the images together.

Whether that be via an image hierarchy or by connecting containers at runtime.

Let's take this one step at a time and do what we want manually first:

``config.yml``:

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
                    - FROM local/cloc-base
                    - ADD . /project
                    - CMD cloc /project

So now we have ``cloc-base`` and ``cloc`` and we have connected the two by having
``FROM local/cloc-base`` inside the ``cloc`` image.

Now we just need to be able to build the ``local/cloc-base`` image so that it is
available before we do ``harpoon build_and_run cloc``.

``actions.py``

    .. code-block:: python

        @an_action
        def build(collector, image, tasks):
            if not image:
                raise BadImage("Please specify an image to work with!")
            if image not in collector.configuration["images"]:
                raise BadImage("No such image", wanted=image, available=list(collector.configuration["images"].keys()))
            image = collector.configuration["images"][image]

            harpoon = collector.configuration["harpoon"]
            image.build(harpoon)

.. note:: We're repeating ourselves quite a bit here, but it's fine for now,
 we'll clean it up later on.

so now we can do ``harpoon build cloc-base`` followed by
``harpoon build_and_run cloc``

Now let's make the ``harpoon build cloc-base`` happen automatically.

First step, as always, is the configuration. Let's do this:

``config.yml``:

    .. code-block:: yaml

        ---

        tag_prefix: local

        images:
            cloc-base:
                [..]

            cloc:
                [..]

                commands:
                    - [FROM, "{images.cloc-base}"]
                    - ADD . /project
                    - CMD cloc /project

And let's change our commands specification from ``listof(string_spec())`` to
something a bit more complicated:

``option_spec/command_objs.py``

    .. code-block:: python

        from harpoon.formatter import MergedOptionStringFormatter
        from harpoon.errors import BadOption

        from input_algorithms import spec_base as sb
        from input_algorithms.dictobj import dictobj
        import six

        class Command(dictobj):
            fields = ["instruction", "params"]

        class array_command_spec(object):
            """Spec for specifying an array of [INSTRUCTION, PARAMS]"""
            def normalise(self, meta, val):
                # Make sure it's atleast a list of strings
                val = sb.listof(sb.string_spec()).normalise(meta, val)

                # Make sure it has exactly two items
                if len(val) != 2:
                    raise BadOption("Array command must be two items", got=len(val), meta=meta)

                # Format the second item into the configuration
                val[1] = sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter).normalise(meta.indexed_at(1), val[1])
                return Command(val[0], val[1])

        class string_command_spec(object):
            """Spec for specifying a string of 'INSTRUCTION PARAMS' """
            def normalise(self, meta, val):
                val = sb.string_spec().normalise(meta, val)

                if " " not in val:
                    raise BadOption("String command must have atleast one space in it", got=val, meta=meta)

                split = val.split(" ", 1)
                return Command(split[0], split[1])

        def command_spec():
            """Spec for specifying a command"""
            return sb.match_spec(
                  (six.string_types, string_command_spec())
                , (list, array_command_spec())
                )

        commands_spec = lambda: sb.listof(command_spec())

So we've defined a ``commands_spec`` at the bottom here that is a list of
``command_spec``, which itself is defined as either strings or lists. Where
strings are normalised with ``string_command_spec`` and lists are normalised
with ``array_command_spec``.

Either way, we end up with a list of ``Command`` objects.

We can do one better and wrap this list in a container that then knows how to
work with the list of ``Command`` objects:

``option_spec/command_objs.py``

    .. code-block:: python

        class Commands(dictobj):
            fields = ["commands"]

        [..]

        commands_spec = lambda: sb.container_spec(Commands, sb.listof(command_spec()))

Now let's use this ``commands_spec``:

``option_spec/image_objs.py``:

    .. code-block:: python

        from harpoon.option_spec.command_objs import commands_spec

        [..]

        image_spec = sb.create_spec(Image
            ...
            , commands = commands_spec()
            )

Now instead of being a list of strings, ``image.commands`` is a ``Commands``
object.

So let's fix our ``image.dockerfile`` implementation to use this new object:

``option_spec/command_objs.py``:

    .. code-block:: python

        class Command(dictobj):
            fields = ["instruction", "params"]

            @property
            def line(self):
                if isinstance(self.params, six.string_types):
                    return " ".join([self.instruction, self.params])
                else:
                    return " ".join([self.instruction, self.params.tag])

        class Commands(dictobj):
            fields = ["commands"]

            @property
            def lines(self):
                return "\n".join(command.line for command in self.commands)

``option_spec/image_objs.py``:

    .. code-block:: python

        class Image(dictobj):
            [..]

            @contextmanager
            def dockerfile(self):
                with hp.a_temp_file() as fle:
                    fle.write(self.commands.lines)
                    [..]

Now run ``harpoon build_and_run cloc`` again, it should work!

Automatically build dependencies
--------------------------------

Now we have the information necessary to automatically build our ``cloc-base``
dependency when we decide to run ``cloc``.

``option_spec/image_objs.py``:

    .. code-block:: python

        class Image(dictobj):
            [..]

            def dependencies(self):
                parent_image = self.commands.parent_image
                if isinstance(parent_image, Image):
                    yield parent_image

Now, let's define ``commands.parent_image``:

``option_spec/command_objs.py``

    .. code-block:: python

        class Commands(dictobj):
            [..]

            @property
            def parent_image(self):
                for command in self.commands:
                    if command.instruction == "FROM":
                        return command.params

And finally let's build this dependency automatically:

``option_spec/image_objs.py``

    .. code-block:: python

        class Image(dictobj):
            [..]

            @an_action
            def build(self, harpoon):
                for dependency in self.dependencies():
                    dependency.build(harpoon)

                [..]

Now run ``harpoon build_and_run cloc`` and you'll see it build ``cloc-base`` as
well.

Showing the layers
------------------

One last thing before we finish section3, let's make a ``show`` action that
shows us the hierarchy of images in our configuration.

Let's start with a new file:

``layers.py``

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

This is code straight from the Harpoon code base and is well tested. It actually
comes from a project made before Harpoon was started and it works well.

It takes in a dictionary of all the available images and expects each image to
have a ``dependencies`` function that returns an iterator of dependencies in the
form of their name in the ``images`` dictionary.

So let's change our ``dependencies`` method on Image:

``option_spec/image_objs.py``

    .. code-block:: python

        class Image(dictobj):
            [..]

            def dependencies(self, images):
                parent_image = self.commands.parent_image
                if isinstance(parent_image, Image):
                    return parent_image.name

But wait! We haven't defined a ``name`` property on our images yet, we should
do that!

``option_spec/image_objs.py``:

    .. code-block:: python

        class Image(dictobj):
            fields = ["name", "tag", "context", "command", "commands"]

            [..]

        image_spec = sb.create_spec(Image
            , name = sb.formatted(sb.overridden("{_key_name_1}"), formatter=MergedOptionStringFormatter)
            ...
            )

There we go, just using our ``_key_name_n`` feature to make sure ``name`` is
always the name of the image.

Now, let's make our ``build`` method able to find the images from our
dependencies:

``actions.py``

    .. code-block:: python

        @an_action
        def build(....)
            [..]

            image.build(harpoon, collector.configuration["images"])

        @an_action
        def build_and_run(....)
            [..]

            image.build(harpoon, collector.configuration["images"])
            image.run()

``option_spec/image_objs.py``

    .. code-block:: python

        class Image(dictobj):
            [..]

            def build(self, harpoon, images):
                for dependency in self.dependencies():
                    images[dependency].build(harpoon, images)

                [..]

Now ``harpoon build_and_run cloc`` should work again. Let's make our show action

``actions.py``

    .. code-block:: python

        from harpoon.layers import Layers

        @an_action
        def show(collector, image, tasks):
            layers = Layers(collector.configuration["images"])
            layers.add_all_to_layers()
            for index, layer in enumerate(layers.layered):
                print("Layer {0}".format(index+1))
                for _, image in layer:
                    print("\t{0}".format(image.name))
                print("")

Now we can do ``harpoon show``.

Circular dependencies
---------------------

Now go into config.yml and do this:

``config.yml``

    .. code-block:: yaml

        cloc-base:
            commands:
                - [FROM, "{images.cloc}"]

And run ``harpoon build_and_run cloc``!

You probably expected some kind of max stack depth error, but what you got instead
was it complaining about ``tag`` not being an attribute of ``MergedOptions``.

This is because it's still converting ``images.cloc-base`` when ``cloc`` tries
to interactive with the ``cloc-base`` Image object.

Either way, it should be an error that you've created a circular dependency.

This module is big enough already, so we'll deal with this problem in the next
section.

