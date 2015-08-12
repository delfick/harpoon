.. _bh_s1_setup_env:

S1: Setup Environment
=====================

Before we touch any Docker we need to first ensure that we have some basic
Python knowledge and we have a foundation which we can work from.

So please read through this section and play along, even if you already know
Python!

First we must setup our environment.

If you're on a Mac::

    $ brew install python-pip
    $ pip install virtualenv

If you're on a Linux::

    $ apt-get install python-setuptools
    $ sudo easy_install pip
    $ pip install virtualenv

If you're on a Windows: https://pip.pypa.io/en/latest/installing.html::

    $ pip install virtualenv

Next, let's create a virtualenv somewhere::

    $ mkdir harpoon-clone
    $ cd harpoon-clone
    $ virtualenv -p $(which python) venv
    $ source venv/bin/activate

The ``venv`` will contain your ``virtualenv``. This is essentially a namespace
for installing python libraries into without installing them globally.

Just make sure that you always start a terminal session with
``source venv/bin/activate`` to ``activate`` the virtualenv.

Once it's activate, we can now use Python::

    $ python

Feel free to play around in the REPL for a while, it'll be your friend when
you're trying to work out Python semantics.

Hello World!
------------

Put this in ``a.py`` and run ``python a.py``:

.. code-block:: python

    print("hello world")

Congratulations! You have implemented the cliché introductory program.

Now, let's learn about the ``__name__`` variable.

Change the code in ``a.py`` to say:

.. code-block:: python

    print("My name is: ", __name__)

Now before you run it, what do you expect it to print?

I expect you'll probably think it'll print out something along the lines of
``My name is: a``.  But, if you ``python a.py`` you'll see that it prints
``My name is: __main__``!

Now, open up the python interpretor and tell it to ``import a``::

    $ python
    > import a

The lesson to learn is that if you are executing a python file, it's __name__ is
__main__, whereas if you import a file, it's __name__ is the name of that file.

This is useful if you want to avoid import time side effects, but still want to
actually execute something.

So, get rid of you ``a.py`` and let's replace it with ``harpoon.py``:

.. code-block:: python

    def main():
        print("Harpoon!")

    if __name__ == "__main__":
        main()

Now, ``python harpoon.py`` will execute our ``main`` function and this is where
the entry point to our Harpoon will go and it means we can import things from
harpoon without fear of it actually running Harpoon.

Python shebang
--------------

We can avoid writing ``python harpoon.py`` and just write ``./harpoon.py`` if we
add a ``shebang`` to the top of the file and make ``harpoon.py`` executable.


So let's do that:

.. code-block:: python

    #!/usr/bin/env python

    def main():
        print("Harpoon!")

    if __name__ == "__main__":
        main()

and from the terminal::

    $ chmod +x harpoon.py

Now run ``./harpoon.py``.

Getting input
-------------

Now for a contrived example so we can get used to simple Python syntax! Let's
get some input from the command line.

.. note:: There's a module for doing just this called ``argparse``, but that'll
  be introduced later and for now we just care about basic syntax.

Let's start with getting the arguments passed into our program:

.. code-block:: python

    import sys

    def main():
        print(sys.argv)

Now execute the following and observe the output: ``./harpoon.py hello there these are arguments``

This time, let's introduce a for loop.

.. code-block:: python

    def main():
        for item in sys.argv:
            print("---")
            print(item)

``./harpoon.py I understand what is happening``

And enumerate:

.. code-block:: python

    def main():
        for index, item in enumerate(sys.argv):
            print(index, item)

And len:

.. code-block:: python

    def main():
        num_arguments = len(sys.argv)
        print("I got {0} arguments".format(num_arguments))

Let's introduce an if statement:

.. code-block:: python

    def main():
        for item in sys.argv:
            if item == "tick":
                print("BOOM!!!!!!!")
            else:
                print("Not a tick")

``./harpoon.py clock tock tick``

And, finally, popping an array:

.. code-block:: python

    def main():
        nxt = None
        while sys.argv:
            nxt = sys.argv.pop()
            print(nxt)

        if nxt is None:
            # This if statement will never be true!
            # Do you know why?
            # Hint: it's something to do with sys.argv
            print("I have no arguments :(")

``./harpoon.py one two three four``

Now you should have enough information to implement ``main`` to satisfy the
following:

* It prints an error if you have less than 2 arguments
* If ``--name`` appears in sys.argv, then a variable is set to the next
  argument in sys.argv
* If ``--name`` doesn't appear in sys.argv then print an error.
* Otherwise print the supplied name to the screen

