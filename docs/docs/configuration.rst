.. _configuration:

Configuration
=============

Harpoon is configured via a YAML file that contains Harpoon configuration
and configuration for each docker image.

The ``Harpoon`` options below can be configured inside your configuration under
a ``harpoon`` section, but most options will be overridden with what is provided
by the command line.

However, these can be overridden on a per task basis with the ``overrides``
option for the task.

The ``Image`` options below are what is available per image:

.. code-block:: yaml

    ---

    images:
        <image_name>:
            <image_options>

.. show_specs::
