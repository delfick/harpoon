Contributions
=============

All contribution is encouraged!

Especially those to documentation and tests, but can be as simple as a feature
request in the issue tracker.

Setting up for development can be as simple as::

  $ pip install virtualenvtools
  $ mkvirtualenv harpoon
  $ pip install -e .
  $ pip install -e ".[tests]"

.. note:: ``pip install -e .`` is equivalent to putting a symlink to the code in
  the PYTHONPATH.

Then running the tests is::

  $ ./test.sh

.. note:: ``from nose.tools import set_trace; set_trace()`` is your friend and
  will throw you into an interactive debugger.

This project heavily uses a couple libraries in particular that are also good
to ``pip install -e .`` into your virtualenv.

option_merge
  https://github.com/delfick/option_merge

  Used to treat multiple sources of data as one piece of data.

  It handles merging all the data and lazily converting it into objects for use.

input_algorithms
  https://github.com/delfick/input_algorithms

  Used to define specifications that sanitise, validate and normalise the data.

You can also run the tests against multiple versions of python by doing::

  $ pip install tox
  $ tox

