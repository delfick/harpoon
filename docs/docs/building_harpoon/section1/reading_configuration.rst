.. _bh_s1_reading_configuration:

S1: Reading Configuration
=========================

Ok, our script is all well and good at the moment but one of the fundamental
concepts of Harpoon is the configuration file.

So let's add one of those!

First, let's start with something basic:

.. code-block:: yaml

    ---

    tag: local/lolz

    commands:
        - FROM gliderlabs/alpine:3.1
        - RUN apk-install figlet --update-cache --repository http://dl-3.alpinelinux.org/alpine/edge/main/
        - CMD figlet lolz

Write the above to ``config.yml``.

Now, to read in yaml involves the PyYaml library, so let's add that to our
``requirements.txt``::

    PyYAML==3.11
    docker-py==1.2.2
    dockerpty==0.3.4
    requests[security]

and do a ``pip install -r requirements.txt`` again to install the external
dependency.

Now, we're finally ready to load in our configuration:

.. code-block:: python

    import yaml

    def main():
        # Get the configuration
        config = yaml.load(open("./config.yml"))

        tag = config["tag"]
        dockerfile_commands = config["commands"]

        # Use the configuration
        [..]

It's an exercise up to you to use our new ``tag`` and ``dockerfile_commands``
variables in our usage of the docker library.

Argparse and argv
-----------------

We still have one more hard coded item we should turn into a user input and that
is the location of the config file.

This is a perfect opportunity for arguments from the command line and we could
do something like what we did for the first section of this guide. However,
manually playing around with ``sys.argv`` is barbaric!

Instead, we'll use the ``argparse`` module:

.. code-block:: python

    import argparse
    import yaml

    def main():
        parser = argparse.ArgumentParser(description="My harpoon")
        parser.add_argument("--config"
            , help = "Location of the configuration file"
            , type = argparse.FileType('r')
            , default = "./config.yml"
            )
        args = parser.parse_args()
        config_file = args.config
        config = yaml.load(config_file)

        [..]

``./harpoon.py --help``

``./harpoon.py --config ./config.yml``

``./harpoon.py``

Short module
------------

This is a short module. After the first recap I'm gonna introduce a couple
libraries I use in Harpoon that streamlines the process of getting, normalising,
validating, and using the data from the configuration file.

For now, play around with the config file and see how it fails spectacularly when
you put wrong data in the configuration file.
