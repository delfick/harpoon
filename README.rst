Harpoon
=======

An opinionated wrapper around the docker-py API that lets you use YAML to define
images and run tasks.

.. image:: https://travis-ci.org/realestate-com-au/harpoon.png?branch=master
    :target: https://travis-ci.org/realestate-com-au/harpoon

See http://harpoon.readthedocs.io for the full documentation.

Installation
------------

Just use pip::

    $ pip install docker-harpoon

Configuration
-------------

Before Harpoon can be used, it must be configured. Configuration is obtained
from the following locations in the following order of precedence:

* Provided --harpoon-config value
* HARPOON_CONFIG environment variable
* ./harpoon.yml

Further, you can also define user-wide settings in your home directory at
``~/.harpoonrc.yml``. For example if you want the "dark" theme for the logging:

.. code-block:: yaml

    ---

    term_colors: dark

The contents of the harpoon config has only one mandatory option, ``images``.
This must be a dictionary of ``image_alias`` to ``image_options``:

.. code-block:: yaml

    ---

    images:
      cacafire:
        commands:
          - FROM ubuntu:14.04
          - RUN apt-get update && apt-get -y install caca-utils
          - CMD cacafire

A rough overview of all the options available can be found at
http://harpoon.readthedocs.org/en/latest/docs/configuration.html

Usage
-----

Once harpoon is installed, there will be a new program called ``harpoon``.

When you call harpoon without any arguments it will print out the tasks you
have available.

Unless you don't have a config file, in which case it'll complain you have no
configuration file.

Once you have a valid configuration file and have chosen a task you wish to
invoke, you may use the ``--task`` cli option to invoke that task::

    $ harpoon --task <task>

Most tasks will also require you to specify an image to work with::

    $ harpoon --task <task> --image <image_alias>

Simpler Usage
-------------

To save typing ``--task`` and ``--image`` too much, the first positional argument
is treated as ``task`` (unless it is prefixed with a dash) and the second
positional argument (if also not prefixed with a dash) is taken as the ``image``.

So::

    $ harpoon --task run --image my_amazing_image

Is equivalent to::

    $ harpoon run my_amazing_image

Tests
-----

Install testing deps and run the helpful script::

    $ pip install -e .
    $ pip install -e ".[tests]"
    $ ./test.sh
    $ ./docker_tests.sh

Or use tox::

    $ pip install tox
    $ tox

