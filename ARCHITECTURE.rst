Architecture
============

Harpoon is structured such that the collection of data, normalisation of data and
it's eventual use are separate concerns.

The sequence of events are as follows:

executor.py
  The mainline sets up logging, argument parsing and sets up the ``Overview``
  object before starting it.

overview.py
  Defines the ``Overview`` object, which will collect configuration from the
  user's home folder, the specified location of ``harpoon.yml``, as well as any
  extra files specified by ``harpoon.yml``.

  It will also install "converters" used to lazily convert the data into objects
  on access.

  .. note:: Images are converted such that they are layered with:

    * The root of the configuration
    * The image options

  Overview will then find the chosen task from the commandline and run it.

option_spec/task_objs.py
  The object representing a task is here. It will layer settings such that we
  have the following layers:

  * The root of the configuration
  * Options from the task on top of the chosen image options
  * Cli arguments on top of the root
  * Overrides from the task on top of the root

  The actual task functionality is then executed.

tasks.py
  The functionality of each task (run, make, push, pull, etc) are defined here
  and are annotated by the ``a_task`` decorator.

  The tasks will then make things happen.

The specifications
------------------

The specifications for what the data should look like lives in
``option_spec.harpoon_specs`` and includes specifications for tasks, images and
the harpoon object.

Find the ``convert_task``, ``convert_image`` and ``convert_harpoon`` functions in
``overview.py`` to see where these specifications are used to normalise the data.

The specifications will create the objects that are defined in ``option_spec.image_objs``
and ``option_spec.task_objs``. The image spec also uses specifications defined
in ``option_spec.image_specs``.

The idea is that conditions around representation of the data is done by the
specs and conditions around the use of the data is done by the objects.

The docker functionality
------------------------

Everything in the ``harpoon.ship`` module is related to working with docker.

Harpoon uses the ``docker-py`` library to interface with the docker server, and
it uses the ``dockerpty`` library to display a tty to the user.

