.. _bh_s1_introduce_delfickapp:

S1: Introduce DelfickApp
========================

Ok, so now we have over 100 (slightly messy) lines of code and we haven't even
started to do anything crazy with the command line options yet, so let's
introduce something to help clean this up for us.

Add this to your ``requirements.txt`` and do yet another
``pip install -r requirements.txt``::

    delfick_app==0.6.6

This library provides the ``App`` class which implements the basics of logging,
the mainline and argument parsing. It's source code can also be found in a single
file over at https://github.com/delfick/delfick_app/blob/master/delfick_app.py#L31

And it's documentation can be found at https://delfick_app.readthedocs.org.

It has quite a few features, but for now we'll just focus on what it replaces in
our implementation so far.

So, let's start from scratch.

.. note:: If you haven't been doing git commits so far, now is a good time to
 git init, git commit and delete the contents of harpoon.py :)

So, now in our empty file, let's add:

.. code-block:: python

    #!/usr/bin/env python

    from delfick_app import App
    import logging

    log = logging.getLogger("harpoon")

    class Harpoon(App):
        def execute(self, args_obj, args_dict, extra_args, logging_handler):
            log.info("Hello world!")

    main = Harpoon.main
    if __name__ == "__main__":
        main()

``./harpoon.py --help``

``./harpoon.py``

You should notice that it's already setup logging to be colorful and it's already
got some command line options.

Now let's add back our configuration:

.. code-block:: python

    import argparse
    import logging
    import yaml

    log = logging.getLogger("harpoon")

    class Harpoon(App):
        def execute(self, args_obj, args_dict, extra_args, logging_handler):
            log.info("Loading configuration from %s", args_obj.config)
            config = yaml.load(args_obj.config)
            tag = config["tag"]
            dockerfile_commands = config["commands"]

        def specify_other_args(self, parser, defaults):
            parser.add_argument("--config"
                , help = "Location of the configuration"
                , type = argparse.FileType('r')
                , default = "./config.yml"
                )

And let's add the rest of our docker stuff:

.. code-block:: python

    from delfick_error import DelfickError

    class BadImage(DelfickError):
        desc = "Something wrong with the image"
    class BadContainer(DelfickError):
        desc = "Something wrong with the container"

    def make_client():
        [..]

    class Harpoon(App):
        def execute(self, args_obj, args_dict, extra_args, logging_handler):
            [..]

            client = make_client()

            dockerfile = tempfile.NamedTemporaryFile(delete=True)
            dockerfile.write("\n".join(dockerfile_commands))
            dockerfile.flush()
            dockerfile.seek(0)

            log.info("Building an image: %s", tag)
            try:
                for line in client.build(fileobj=dockerfile, rm=True, tag=tag, pull=False):
                    print(line)
            except docker.errors.APIError as error:
                raise BadImage("Failed to build an image", tag=tag, error=error)

            log.info("Making a container from an image (%s)", tag)
            try:
                container = client.create_container(image=tag)
            except docker.errors.APIError as error:
                raise BadContainer("Failed to build a container", image=tag, error=error)

            log.info("Starting a container: %s", container["Id"])
            try:
                dockerpty.start(make_client(), container)
            except docker.errors.APIError as error:
                raise BadContainer("Failed to start the container", container=container["Id"], image=tag, error=error)

            log.info("Cleaning up container: %s", container["Id"])
            try:
                client.remove_container(container)
            except docker.errors.APIError as error:
                log.error("Failed to remove the container :(\tcontainer=%s\terror=%s", container["Id"], error)

Note that we don't have to do the big try..except anymore. It's done for us by
delfick_app! https://github.com/delfick/delfick_app/blob/master/delfick_app.py#L227

Finally, let's make requests shut up again:

.. code-block:: python

    class Harpoon(App):
        def setup_other_logging(self, args_obj, verbose=False, silent=False, debug=False):
            logging.getLogger("requests").setLevel([logging.ERROR, logging.INFO][verbose or debug])

In DelfickApp, verbose and debug are two distinct options where tracebacks are
only risen if debug is set. Here we're making it so that ``requests`` only
shows ``INFO`` logging if neither verbose or debug are set, otherwise it is set
to only show ``ERROR`` logging.
