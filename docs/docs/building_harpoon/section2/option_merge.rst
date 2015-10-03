.. _bh_s2_option_merge:

S2: Option Merge
================

I have one more library to introduce to you: OptionMerge.

This is a library I made to represent many dictionaries as one dictionary. I'll
show you how to use it and then I'll explain what's happening.

First, we add it to our ``setup.py``:

.. code-block:: python

    , install_requires =
      [ "option_merge==0.9.8.2"
      .....
      ]

and the basic usage is really simple:

.. code-block:: python

    from option_merge import MergedOptions

    options1 = {"a": 1}
    options2 = {"a": 2, "b": 3}
    options3 = {"c": 4}

    options = MergedOptions.using(options1, options2, options3)

    print(options["a"])
    print(options["b"])
    print(options["c"])

Execute that script! You should get something like this printed::

    2
    3
    4

Here are some more things you can do with this object:

.. code-block:: python

    # We can not use the ``using`` helper if we choose to
    # This is handy if we're adding options at different times
    options = MergedOptions()
    options.update(options1)
    options.update(options2)
    options.update(options3)

    # We can set deeply nested values
    options[["one", "two", "three"]] = "four"
    print(options["one"].as_dict())
    # Prints {"one": {"two": {"three": "four"}}}

    # We can access deeply nested things with strings
    print(options["one.two.three"])
    print(options[["one", "two", "three"]])
    # Both Print "four"

This is how Harpoon manages inter-document referencing, by making the entire
configuration a MergedOptions object and then just accessing strings against it.

The initial version of option_merge would split the key by dot to determine what
to access, but this meant keys couldn't have dots in them, so after a rewrite,
access is now done via longest match.

I'll demonstrate the implications of this below:

.. code-block:: python

    options = MergedOptions.using({
          "ubuntu":
          { "trusty":
            { "14":
              { "04": 1
	      , "06": 4
              }
            }
          }
        , "ubuntu.trusty.14.04": 2
        , "ubuntu.trusty.14.05": 3
        })

    print(options["ubuntu.trusty.14.04"])
    # prints 2

    print(options["ubuntu.trusty.14.05"])
    # prints 3

    print(options["ubuntu.trusty.14.06"])
    # prints 4

This means whenever you set a key in a ``MergedOptions`` object you must use the
array syntax to seperate the key otherwise it'll make a dotted key:

.. code-block:: python

    options = MergedOptions()
    options["ubuntu.trusty"] = 1
    options[["debian", "lenny"]] = 2

    print(options.as_dict())
    # prints {"ubuntu.trusty": 1, "debian": { "lenny": 2 } }

How option_merge works
----------------------

So option_merge works by creating a data structure and then exposing a viewer
API for accessing that data.

What this means is that MergedOptions is an object with two attributes:

storage

    The underlying storage data structure that holds references to the original
    data

prefix

    The path into the storage that this MergedOption is looking at

When you access a dictionary with a MergedOptions object you get back a new
Mergedoptions object with the same storage, but a different prefix. I.e. it's
Viewing a different part of the storage.

This means when you access something on a MergedOptions object you are always
looking at the most up to date values in the underlying storage.

OptionMerge also has a feature where you can compute the value at some key and
then cache the value you computed. This feature is called converters.

The underlying storage holds a Converters object which holds a cache of computed
values and the converters that do the computation. You can access it via the
MergedOptions object and add converters.

A converter is an object with two things:

convert

    A function that takes the data originally at that key and returns the new
    value for that key

path

    The path that will invoke this conversion

We can add a converter like this:

.. code-block:: python

    from option_merge.converters import Converter
    from option_merge import MergedOptions

    options = MergedOptions.using({"a": 1, "b": 2})

    def convert(path, data):
        return data * 2
    converter = Converter(convert, ["a"])
    options.converters.append(converter)

    # Once all the converters are added, we activate them
    options.converters.activate()

    # Now we can get our value
    print(options["a"])
    print(options["a"])
    # Both print 2

Note that converters need to be activated before they work. Before this point
the underlying storage will ignore them.

And before you ask, they don't support globs. I tried to implement that once,
it was surprisingly difficult to implement correctly.

Introducing dictobj
-------------------

So let's see what happens when we have a value in our options that is not a
dictionary, but instead an object with attributes:

.. code-block:: python

    class Image(object):
        def __init__(self, one):
            self.one = one

    options = MergedOptions.using({"image": Image(1)})

    print(options["image.one"])

You should have got a KeyError! MergedOptions only supports accessing deeply
nested keys via dictionary syntax (i.e. with the square brackets).

This means our ``Image`` object needs to be a type of dictionary for our inter-
document referencing to work:

.. code-block:: python

    from input_algorithms.dictobj import dictobj

    class Image(dictobj):
        fields = ["one"]

    options = MergedOptions.using({'image': Image(1)})

    print(options["image.one"])
    # Prints 1

That's better! ``input_algorithms`` contains a class called ``dictobj`` which we
can inherit from. This class is special because instances of it allow
dictionary and object access of it's attributes:

.. code-block:: python

    class Image(dictobj):
        fields = ["one", "two"]

    image = Image(1, 2)
    print(image.one)
    print(image.two)
    print(image["one"])
    print(image["two"])
    # Prints 1 then 2 then 1 then 2

We also don't have to write an annoyingly empty ``__init__`` method. All we have
to do is specify what fields we expect and ``dictobj`` does the rest of setting
those fields on the instance when the object is instantiated.

Improving Collector
-------------------

Before we end this section and enter section3, let's put option_merge into
action by using the Collector helper it provides.

So, let's replace ``collector.py`` with this:

.. code-block:: python

    from harpoon.option_spec.image_objs import image_spec
	from harpoon.actions import available_actions

    from option_merge.collector import Collector
    from option_merge import MergedOptions
    from input_algorithms.meta import Meta
    import yaml

    class Collector(Collector):
        def read_file(self, location):
            return yaml.load(location)

        def start_configuration(self):
            return MergedOptions()

        def add_configuration(self, configuration, collect_another_source, done, result, src):
            configuration.update(result)

        def extra_prepare(self, configuration, cli_args):
            configuration.update(
                  { "harpoon": cli_args["harpoon"]
				  , "cli_args": cli_args
                  }
                )

        def extra_configuration_collection(self, configuration):
            meta = Meta(configuration, [])
            configuration["image"] = image_spec.normalise(meta, self.configuration)

        def start(self):
            cli_args = self.configuration["cli_args"]
            chosen_task = self.configuration["harpoon"]["task"]
            available_actions[chosen_task](self, cli_args)

And let's replace ``execute`` in ``executor.py`` with this:

.. code-block:: python

    class Harpoon(App):
        [..]

        def execute(self, args, extra_args, cli_args, logging_handler):
            cli_args['harpoon']['make_client'] = make_client

            collector = Collector()
            collector.prepare(args.config.name, cli_args)
            collector.start()

The ``Collector`` class in ``option_merge.collector`` is a helper class that
provides a number of hooks that can be overridden. You can find the source for
this class over at https://github.com/delfick/option_merge/blob/master/option_merge/collector.py

Finally, we have enough information for section3, where we'll start implementing
some more Harpoon centric ideas like multiple images, context control and
custom tasks.
