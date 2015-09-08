.. _bh_s3_multiple_images:

S3: Multiple Images
===================

Let's make our config look like this:

.. code-block:: yaml

    images:
        mine:
            tag: local/lolz

            commands:
                - FROM gliderlabs/alpine:3.1
                - RUN apk-install figlet --update-cache --repository http://dl-3.alpinelinux.org/alpine/edge/main/
                - CMD figlet lolz

And let's add an image cli argument in ``executor.py``:

.. code-block:: python

    class Harpoon(App):
        cli_categories = ["harpoon"]
        cli_positional_replacements = [('--task', 'list_tasks'), '--image']

        [..]

        def specify_other_args(self, parser, defaults):
            [..]

            parser.add_argument("--image"
                , help = "The image to work with"
                , dest = "harpoon_image"
                , **defaults["--image"]
                )

Note that we also make the second positional argument map to '--image'. However
for this argument there is no default value.

Now inside ``collector.py``:

.. code-block:: python

    class Collector(Collector):
        [..]

        def extra_configuration_collection(self, configuration):
            meta = Meta(configuration, [])
            if "images" in configuration:
                for image in configuration["images"]:
                    configuration["images"][image] = image_spec.normalise(meta, configuration["images"][image])

And finally, in ``actions.py``:

.. code-block:: python

    @an_action
    def build_and_run(collector, cli_args):
        image = collector.configuration["images"][cli_args["harpoon"]["image"]]

        [..]

And magic bananas! we can do ``harpoon build_and_run mine``.

Error Checking
--------------

Now let's perhaps give better errors when things aren't perfect!

First, let's create a new error class in ``errors.py``:

.. code-block:: python

    class BadConfiguration(DelfickError):
        desc = "Something wrong with the configuration"

and let's change ``collector.py``:

.. code-block:: python

    from harpoon.errors import BadConfiguration

    class Collector(Collector):
        BadConfigurationErrorKls = BadConfiguration

        [..]

        def find_missing_config(self, configuration):
            if "images" not in self.configuration:
                raise self.BadConfigurationErrorKls("Didn't find any images in the configuration")
            if not isinstance(configuration["images"], dict):
                raise self.BadConfigurationErrorKls("images needs to be a dictionary!", got=type(configuration["images"]))

        def extra_configuration_collection(self, configuration):
            meta = Meta(configuration, [])
            for image in configuration["images"]:
                configuration["images"][image] = image_spec.normalise(meta, configuration["images"][image])

Note that we can get rid of the check for "images" in
``extra_configuration_collection`` because we won't get to that part if the check
in ``find_missing_config`` raises an exception.

And finally, in ``actions.py``:

.. code-block:: python

    from harpoon.errors import BadImage

    @an_action
    def build_and_run(collector, cli_args):
        chosen_image = cli_args["harpoon"]["image"]
        if not chosen_image:
            raise BadImage("Please specify an image to work with!")
        if chosen_image not in collector.configuration["images"]:
            raise BadImage("No such image", wanted=chosen_image, available=list(collector.configuration["images"].keys()))
        image = collector.configuration["images"][chosen_image]

        harpoon = cli_args["harpoon"]
        image.build(harpoon)
        image.run(harpoon)

Lazily loading the images
-------------------------

what we have in ``Collector.extra_configuration_collection`` doesn't scale well
when you have many images because it loads all of them regardless of whether
you're using them or not.

So what we can do is instead install converters
(as mentioned in :ref:`bh_s2_option_merge`):

.. code-block:: python

    from option_merge.converter import Converter
    import logging

    log = logging.getLogger("harpoon.collector")

    class Collector(Collector):
        [..]

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

.. note:: We have to create a closure inside the for loop with our ``image``
    variable so that we can use it inside the ``convert_image`` function and so
    that's why we've defined that function in a separate
    ``install_image_converters`` method.

Now we only run ``image_spec.normalise`` when we access that image!

In the next module we're gonna define custom tasks with our configuration.
