.. _bh_s1_logging_and_errors:

S1: Logging and Errors
======================

Ok, so we have a working application but it isn't very informative about what
it's doing and errors result in ugly tracebacks, let's do something about that!

Logging
-------

Logging is fairly simple in Python:

.. code-block:: python

    import logging
    import sys

    log = logging.getLogger("harpoon")

    def main():
        root = logging.getLogger('')
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)-15s %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)

        handler2 = logging.StreamHandler(stream=sys.stdout)
        handler2.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)-15s %(message)s
        log.addHandler(handler2)
        log.setLevel(logging.INFO)
        log.info("Hello there")

        [..]

So what we've done is created a ``log`` object that has methods like ``info``,
``error``, ``warning`` and ``debug`` that we can use to print information to the
screen.

We've also set up the root logger to output to ``sys.stderr`` and have a format
that includes the current time, the ``level`` of the information, the ``name``
of the logger and the ``message`` being outputted.

So let's add some logging to our application:

.. code-block:: python

    def main():
        [..]

        log.info("Loading config from %s", config_file.name)
        config = yaml.load(config_file)

        [..]

        log.info("Building an image: %s", tag)
        for line in client.build(fileobj=dockerfile, rm=True, tag=tag, pull=False):
            print(line)

        log.info("Making a container from an image (%s)", tag)
        container = client.create_container(image=tag, tty=True)

        log.info("Starting a container: %s", container["Id"])
        dockerpty.start(make_client(), container)

        log.info("Cleaning up container: %s", container["Id"])
        client.remove_container(container)

``./harpoon.py``

Your output should look something like::

    2015-07-12 19:49:59,511 INFO    harpoon         Loading config from ./config.yml
    2015-07-12 19:49:59,540 INFO    requests.packages.urllib3.connectionpool Starting new HTTPS connection (1): boot2docker
    2015-07-12 19:49:59,613 INFO    harpoon         Building an image: local/lolz
    {"stream":"Step 0 : FROM gliderlabs/alpine:3.1\n"}

    {"stream":" ---\u003e 0114fb636191\n"}

    {"stream":"Step 1 : RUN apk-install figlet --update-cache --repository http://dl-3.alpinelinux.org/alpine/edge/main/\n"}

    {"stream":" ---\u003e Using cache\n"}

    {"stream":" ---\u003e 6c81500c702b\n"}

    {"stream":"Step 2 : CMD figlet lolz\n"}

    {"stream":" ---\u003e Using cache\n"}

    {"stream":" ---\u003e 010a62b427b5\n"}

    {"stream":"Successfully built 010a62b427b5\n"}

    2015-07-12 19:50:00,162 INFO    harpoon         Making a container from an image (local/lolz)
    2015-07-12 19:50:00,301 INFO    harpoon         Starting a container: 987636259c5607265e9685cd1d2488c61e4bc49c070e9cefda1aa07f2d7a7cb2
    2015-07-12 19:50:00,303 INFO    requests.packages.urllib3.connectionpool Starting new HTTPS connection (1): boot2docker
    2015-07-12 19:50:00,353 INFO    requests.packages.urllib3.connectionpool Starting new HTTPS connection (2): boot2docker
    2015-07-12 19:50:00,405 INFO    requests.packages.urllib3.connectionpool Starting new HTTPS connection (3): boot2docker
    _       _
    | | ___ | |____
    | |/ _ \| |_  /
    | | (_) | |/ /
    |_|\___/|_/___|

    2015-07-12 19:50:00,839 INFO    harpoon         Cleaning up a container: 987636259c5607265e9685cd1d2488c61e4bc49c070e9cefda1aa07f2d7a7cb2

Now, I'm not sure about you, but those requests logging is a bit annoying, we
can get rid of those.

First, let's add a ``--debug`` option:

.. code-block:: python

    def main():
        parser = argparse.ArgumentParser(description="My harpoon!")
        parser.add_argument("--config"
            , help = "Location of the config file"
            , type = argparse.FileType("r")
            , default = "./config.yml"
            )
        parser.add_argument("--debug"
            , help = "Whether to show more information"
            , action = "store_true"
            )
        args_obj = parser.parse_args()

        [..]

So here we've added the ``--debug`` parameter with an ``action`` of ``store_true``.
This means the argument takes no value and if specified will make ``args_obj.debug``
equal to ``True``. Otherwise it will default to ``False``.

Now we've setup that up, let's turn off requests logging:

.. code-block:: python

    def main()
        [..]

        args_obj = parser.parse_args()
        if not args_obj.debug:
            logging.getLogger("requests").setLevel(logging.ERROR)

        [..]

Basically, if we aren't in debug mode then don't show any messages that have a
``level`` more fine grained than ``ERROR``.

Now when you run ``./harpoon.py`` it'll only show those requests logging if you
use ``./harpoon.py --debug``.

Exceptions
----------

Now, you'll have noticed previously when you gave bad information in your
config.yml file then docker would generally complain with a big traceback.

Let's make that go away:

.. code-block:: python

    from __future__ import print_function
    import sys

    def main():
        [..]

        try:
            config = yaml.load(args_obj.config_file)

            [..]

            log.info("Cleaning up a container: %s", container["Id"]
            client.remove_container(container)

        except Exception as error:
            print("Something went wrong!!!", file=sys.stderr)
            print("!" * 80, file=sys.stderr)
            print("{0}: {1}".format(error.__class__.__name__, str(error)), file=sys.stderr)
            sys.exit(1)

Now if say we change the tag in the config.yml to be a list and run ``harpoon.py``
again, then we won't get the traceback anymore!

But, what if we want the traceback? Sometimes tracebacks can be helpful for
debugging purposes:

.. code-block:: python

    except Exception as error:
        if args_obj.debug:
            raise
        else:
            [..]
            sys.exit(1)

In Python, if you ``raise`` without arguments in an ``except`` block, then you
are re-raising the error, and so what will happen here is if ``--debug`` then the
error will be raised to the interpretor and a traceback will be shown.

The unfortunate thing here is that this is a bit crude and we really shouldn't
be doing a catch all.

So let's instead introduce ``delfick_error``. One of my modestly named libraries
that helps with creating arbitrary exceptions. The full source can be found in
a single file at https://github.com/delfick/delfick_error/blob/master/delfick_error.py#L25

So, let's add it to our ``requirements.txt`` and do another
``pip install -r requirements.txt``::

    delfick_error==1.7.1

First step is to define custom exceptions:

.. code-block:: python

    from delfick_error import DelfickError

    class BadImage(DelfickError):
        desc = "Something wrong with the image"
    class BadContainer(DelfickError):
        desc = "Something wrong with the container"

    def main():
        [..]

Next let's catch docker exceptions and turn them into DelfickError exceptions:

.. code-block:: python

    def main():
        try:
            log.info("Building an image: %s", tag)
            try:
                for line in client.build(fileobj=dockerfile, rm=True, tag=tag, pull=False):
                    print(line)
            except docker.errors.APIError as error:
                raise BadImage("Failed to build an image", tag=tag, error=error)

            log.info("Making a container from an image (%s)", tag)
            try:
                container = client.create_container(image=tag, tty=True)
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
        except DelfickError as error:
            [..]

This looks a bit nasty but it means we only print out expected errors and
anything unexpected will actually give something helpful when it fails.

The good news is the next module will remove a fair amount of code for us :)
