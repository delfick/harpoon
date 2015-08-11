.. _building_harpoon:

Building your own Harpoon!
==========================

.. toctree::
	:hidden:

	section1/setup_env
	section1/introduce_dockerpy
	section1/reading_configuration
	section1/logging_and_errors
	section1/introduce_delfickapp
	section1/recap_one

	section2/making_a_package
	section2/choosing_a_task
	section2/making_an_image_object
	section2/validating_input
	section2/option_merge
	section2/recap_two

	section3/multiple_images
	section3/custom_tasks
	section3/formatted_options
	section3/context
	section3/image_dependencies
	section3/recap_three

Welcome to a guide on building your own Harpoon!

Harpoon is a docker client that reads YAML. It is written in Python and offers
the ability to define multiple docker files, inline tasks, control over the
context, and various other pieces of functionality.

This guide exists as a primer on Python, the docker-py library and the several
libraries that were created during the implementation of Harpoon.

It is hoped that by creating your own Harpoon, you'll get some insight into both
what it does and also how it does it.

:ref:`bh_s1_setup_env`
	First we setup a Python environment and explore some Python basics.

:ref:`bh_s1_introduce_dockerpy`
	Next we have a look at the ``docker-py`` and ``dockerpty`` libraries and use
	them to build an image and run a container.

:ref:`bh_s1_reading_configuration`
	Let's start allowing user specified configuration via a Yaml file.

:ref:`bh_s1_logging_and_errors`
	A module on how to do proper logging in Python and make our tracebacks a
	little prettier.

:ref:`bh_s1_introduce_delfickapp`
	This is where we introduce a library that takes care of some of the things
	we've implemented manually!

:ref:`bh_s1_recap_one`
	A little recap of what we've learnt so far

-------------------------------------------------------------------------------

:ref:`bh_s2_making_a_package`
	Let's bring out a setup.py and make an actual python package

:ref:`bh_s2_choosing_a_task`
	Tasks are central to Harpoon, so let's do the necessary plumbing to choose
	a task.

:ref:`bh_s2_making_an_image_object`
	Let's make an object to represent our image. This may seem unecessary now,
	but will make a lot of sense later on.

:ref:`bh_s2_validating_input`
	Let's perhaps show some errors when things are wrong!

:ref:`bh_s2_option_merge`
	The last library to be introduced!

:ref:`bh_s2_recap_two`
	See where we should be at

-------------------------------------------------------------------------------

:ref:`bh_s3_multiple_images`
	Having only one image seems a bit limiting, let's make it support multiple
	images.

:ref:`bh_s3_custom_tasks`
	I want to be able to define tasks inside the configuration

:ref:`bh_s3_formatted_options`
	The time has come to make the config file come alive!

:ref:`bh_s3_context`
	Let's ad files into our images!

:ref:`bh_s3_image_dependencies`
	It's really nice being able to connect images

:ref:`bh_s3_recap_three`
	See the code at this point
