Harpoon
=======

An opinionated wrapper around the docker-py API to docker that knows how to read
yaml files and make things happen.

.. image:: https://travis-ci.org/realestate-com-au/harpoon.png?branch=master
    :target: https://travis-ci.org/realestate-com-au/harpoon

See http://harpoon.readthedocs.org for the full documentation.

Installation
------------

Just use pip::

  pip install docker-harpoon

Usage
-----

Once harpoon is installed, there will be a new program called ``harpoon``.

When you call harpoon without any arguments it will print out the tasks you
have available.

You may invoke these tasks with the ``task`` option.

Simpler Usage
-------------

To save typing ``--task`` and ``--image`` too much, the first positional argument
is treated as ``task`` (unless it is prefixed with a ``-``) and the second
positional argument (if also not prefixed with a ``-``) is taken as the ``image``.

So::

    $ harpoon --task run --image my_amazing_image

Is equivalent to::

    $ harpoon run my_amazing_image

Logging colors
--------------

If you find the logging output doesn't look great on your terminal, you can
try setting the ``term_colors`` option in ``harpoon.yml`` to either ``light`` or
``dark``.

Tests
-----

Install testing deps and run the helpful script::

  pip install -e .
  pip install -e ".[tests]"
  ./test.sh

