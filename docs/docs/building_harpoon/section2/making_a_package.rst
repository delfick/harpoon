.. _bh_s2_making_a_package:

S2: Making a Package
====================

Python has a mechanism for making packages called setuptools which is
conventionally used from a ``setup.py`` at the root of the project.

First, let's make a folder for our harpoon::

    $ mkdir harpoon
    $ mv harpoon.py harpoon/executor.py

.. note:: It's good practise not to have a module in your package with the same
    name as the package to avoid import confusion, so we've renamed harpoon.py
    as executor.py

One last step to making our folder into a package is adding a ``__init__.py``::

    $ touch harpoon/__init__.py

Now let's create our setup.py:

.. code-block:: python

    from setuptools import setup, find_packages

    setup(
          name = "my-harpoon"
        , version = 0.1
        , packages = ['harpoon'] + ['harpoon.%s' % pkg for pkg in find_packages('harpoon')]

        , install_requires =
          [ "delfick_app==0.6.7"
          , "docker-py==1.2.2"
          , "dockerpty==0.3.4"
          , "pyYaml==3.11"
          , "requests[security]"
          ]

        , entry_points =
          { 'console_scripts' :
            [ 'harpoon = harpoon.executor:main'
            ]
          }
        )

I'll list the different sections you're configuring here:

name
    This only makes a real difference when you're uploading your package to the
    python package index (pypi). We won't be doing that, so this value can be
    anything.

version
    Another value that only matters if we're uploading a package.

packages
    Essentially what to include in our package. As with anything in software
    naming is hard and I've been referring to these as modules.

install_requires
    This replaces our ``requirements.txt``, which you can safely remove now!

entry_points
    We use this section to declare what console scripts we want installed.

    The line ``harpoon = harpoon.executor:main`` says make me a script called
    ``harpoon`` that runs the ``main`` function found in the ``harpoon.executor``
    module.

    In our case we have ``main = Harpoon.main`` which defines the ``main`` function
    to be executed.

So now you should have a folder structure that looks like::

    setup.py

    config.yml

    venv/
        <virtualenv contents>

    harpoon/
        executor.py
        __init__.py

So make sure you've activated your venv (``source venv/bin/activate``) and run
``pip install -e .``

This command will install your package into the virtualenv
along with our ``install_requires`` dependencies.

After that we finally have our package installed and our ``harpoon`` script
installed in ``venv/bin``, which is on your ``PATH`` when you activate the
virtualenv.

So now just run ``harpoon``

.. note:: if you encounter error ``raise DistributionNotFound(req)``, It is better to run
  following command firstly.::

    $ sudo apt-get install python-dev libffi-dev
    $ sudo easy_install pyasn1 ndg-httpsclient cryptography


Moving out of execute
----------------------

Let's do two last things before we move onto the next module and move out the
logic in ``executor.Harpoon.execute`` into seperate modules.

First, let's move out our custom error classes into ``harpoon/errors.py``:

.. code-block:: python

    from delfick_error import DelfickError

    class BadImage(DelfickError):
        desc = "Something bad about the image"
    class BadContainer(DelfickError):
        desc = "Something bad about the container"

Next remove those from ``executor.py`` and whilst there, make it have:

.. code-block:: python

    from harpoon.collector import Collector

    [..]

    class Harpoon(App):
        def execute(self, args_obj, args_dict, extra_args, logging_handler):
            collector = Collector()
            collector.prepare(args_obj.config)
            collector.start(make_client)

    [..]

And then let's make ``harpoon/collector.py``:

.. code-block:: python

    from harpoon.errors import BadImage, BadContainer

    import tempfile
    import logging
    import docker
    import yaml

    log = logging.getLogger("harpoon.collector")

    class Collector(object):
        def prepare(self, configfile):
            log.info("Reading configuration from %s", configfile.name)
            self.configuration = yaml.load(configfile)

        def start(self, client_maker):
            tag = self.configuration["tag"]
            dockerfile_commands = self.configuration["commands"]

            client = client_maker()

            dockerfile = tempfile.NamedTemporaryFile(delete=True)
            dockerfile.write("\n".join(dockerfile_commands))
            dockerfile.flush()
            dockerfile.seek(0)

            log.info("Building an image: %s", tag)
            try:
                for line in client.build(fileobj=dockerfile, rm=True, tag=tag):
                    print(line)
            except docker.errors.APIError as error:
                raise BadImage("Failed to build the image", tag=tag, error=error)

            [..]

Now we've separated the mainline from the app itself and further to that,
separated getting the configuration from using the configuration.

In the real harpoon the order of execution is:

* Collect and parse all the configuration
* Find the task that needs to be executed
* Execute that task

So in the next module, we'll start down the path towards having task support.
