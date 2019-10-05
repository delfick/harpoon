.. _tasks:

Tasks
=====

Harpoon's mechanism for doing anything are tasks. By default Harpoon comes with a
number of tasks as describe below:

.. show_tasks:

Custom Tasks
------------

You can add tasks within your container. For example:

.. code-block:: yaml

  ---

  images:
    app:
      commands:
        - FROM some_image:3
        - CMD startup_app

       tasks:
        run_app:
          description: "Startup the app"

        run_tests:
          description: Run the unit tests
          options:
            bash: cd /app && rake tests

Each task has no required options but can be configured with ``action``,
``options``, ``overrides``, ``description`` and ``label``.

If ``action`` or ``options`` are not specified then the task will just create the
image it's defined under and run the default command.

If the ``action`` is specified and is just a string, then it will call that action
and give the ``image`` option as the name of this image. The available tasks are
those in https://github.com/realestate-com-au/harpoon/blob/master/harpoon/tasks.py
with a ``a_task`` decorator. For most cases, you just need the ``run`` task which
is the default value for ``action``.

The tasks defined in these definitions will be shown when you do
"harpoon --task list_tasks".

You may also use extra arbitrary cli options for your tasks with ``{$@}``:

.. code-block:: yaml

  ---

  images:
    app:
      commands:
        ...
      tasks:
        something:
          options:
            bash: cd /app && ./some_script.sh {$@}

Then say you run harpoon like::

  $ harpoon --task something -- --an-option 1

Then it will start up the app container and run::

  $ /bin/bash -c 'cd /app && ./some_script.sh --an-option 1'

Because everything that comes after a ``--`` in the argv to harpoon will be
available as "$@".
