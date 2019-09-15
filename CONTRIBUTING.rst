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

You can also run the tests against multiple versions of python by doing::

  $ pip install tox
  $ tox
