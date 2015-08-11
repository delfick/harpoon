.. _bh_s3_formatted_options:

S3: Formatting Options
======================

Our config is still pretty static at the moment and it's gonna help us for
some future functionality if we can reference other parts of the config inside
the config itself.

Let's start with something simple:

``image_objs.py``:

    .. code-block:: python 

        class formatted_spec(object):
            def normalise(self, meta, val):
                val = sb.string_spec().normalise(meta, val)
                return val.format(**meta.key_names())

        image_spec = create_spec(Image
            , tag = formatted_spec()
            , command = sb.defaulted(formatted_spec(), None)
            , commands = listof(string_spec())
            )

.. note:: We're deliberately leaving the commands unformatted for now.

So now let's change our config to look like this:

.. code-block:: yaml

    ---

    images:
        mine:
            tag: "local/{_key_name_1}"

            commands:
                - FROM gliderlabs/alpine:3.1
                - RUN apk-install figlet --update-cache --repository http://dl-3.alpinelinux.org/alpine/edge/testing/
                - CMD figlet lolz

            tasks:
                hello:
                    description: Say hello
                    options:
                        command: figlet hello

The only difference is ``images.mine.tag`` now has ``"local/{_key_name_1}"`` as
it's value.

The ``meta.key_names`` method returns a dictionary of _key_name_n where
n is a number from 0 upwards. So in the case of our ``tag`` entry,
``meta.key_names()`` will return ``{"_key_name_0": "tag", "_key_name_1": "mine"
, "_key_name_2": "images"}``

Now let's do ``harpoon build_and_run mine``.

And you should notice a line that looks like this::

    11:17:06 INFO    harpoon.option_spec.image_objs Making a container from an image (local/mine)

Which shows us that it successfully formatted the ``{_key_name_1}`` into ``mine``.

Formatting all the configuration!
---------------------------------

This is all well and good, but what if for some reason, we want to format all of
the configuration?

Well, we still have to manually specify some kind of ``formatted_options`` spec,
for each option that is formatted but what we can do is be smarter about how we
format the values.

It so happens that python's format magic is encapsulated in a ``string.Formatter``
class which we can override and customize.

So let's do that in a new file:

``formatter.py``

    .. code-block:: python

       from string import Formatter

        class MergedOptionsFormatter(Formatter):
            def __init__(self, all_options):
                self.all_options = all_options

            def get_field(self, field, args, kwargs):
                return self.all_options[field], ()

This ``get_field`` function is explained over in the python
`documentation <https://docs.python.org/2/library/string.html#string.Formatter.get_field>`_
and takes in the strings wrapped by the curly brackets along with the original
positional and keyword arguments passed into format. We must return a tuple of
two items from this function: The formatted value and the arguments we used.

So usage looks something like this:

.. code-block:: python

    formatter = Mergedoptionsformatter({"one": 1, "two": 2, "three": 3})
    print(formatter.format("{one} two {three}"))
    # prints "1 two 3"

Or with a MergedOptions object:

.. code-block:: python

    options = Mergedoptions.using({"one": {"two": {"three": "four"}, "five": 5}})
    formatter = Mergedoptionsformatter(options)
    print(formatter.format("{one.two.three} and {one.five}"))
    # prints "four and 5"

So, let's use this formatter:

``option_spec/image_objs.py``

    .. code-block:: python

        from harpoon.formatter import Mergedoptionsformatter

        class formatted_spec(object):
            def normalise(self, meta, val):
                val = sb.string_spec().normalise(meta, val)
                options = meta.everything.wrapped()
                options.update(meta.key_names())
                return MergedoptionsFormatter(options).format(val)

So now we can format arbitrary things from our configuration!

``config.yml``

    .. code-block:: yaml

        ---

        tag_prefix: local

        images:
            mine:
                tag: "{tag_prefix}/{_key_name_1}"

                commands:
                    - FROM gliderlabs/alpine:3.1
                    - RUN apk-install figlet --update-cache --repository http://dl-3.alpinelinux.org/alpine/edge/testing/
                    - CMD figlet lolz

                tasks:
                    hello:
                        description: Say hello
                        options:
                            command: figlet hello

                    config_root:
                        description: Say where the config is
                        options:
                            command: "figlet {config_root}"

So here, we're using this feature in two places. Firstly, we've defined a
``tag_prefix`` at the top of the file, which we then reference in ``images.mine.tag``.

The second place is in this new ``config_root`` task, which takes advantage of a
feature provided by the ``Collector`` to display the folder your configuration
sits in. (See this
`line of code <https://github.com/delfick/option_merge/blob/1afba93969dcb320bef0768fe58c19c82c9b317e/option_merge/collector.py#L130>`_
)

Advanced formatting
-------------------

So what we have is great, but what if we reference a value that itself needs to
be formatted?

Or if the value being formatted doesn't exist?

Or if we want to have custom format specifications?

Well, this is where ``option_merge.formatter.MergedOptionStringFormatter``
becomes your friend.

It's a class that requires you to implement three methods:

.. code-block:: python

    from harpoon.errors import BadOptionFormat

    from option_merge.formatter import MergedOptionStringFormatter
    from input_algorithms.meta import Meta

    class MergedOptionStringFormatter(MergedOptionStringFormatter):
        def get_string(self, key):
            """Get a string from all_options"""
            if key not in self.all_options:
                kwargs = {}
                if len(self.chain) > 1:
                    kwargs['source'] = Meta(self.all_options, self.chain[-2]).source
                raise BadOptionFormat("Can't find key in options", key=key, chain=self.chain, **kwargs)

            return super(MergedOptionStringFormatter, self).get_string(key)

        def special_get_field(self, value, args, kwargs, format_spec=None):
            """Also take the spec into account"""
            if value in self.chain:
                raise BadOptionFormat("Recursive option", chain=self.chain + [value])

        def special_format_field(self, obj, format_spec):
            """Know about any special formats"""
            pass

I'll leave it up to you to define ``BadOptionFormat``!

This implementation takes advantage of two properties on this class:

``all_options``

    This is the root of the configuration as passed into this instance of the
    Formatter

``chain``

    The formatter keeps track of the keys that were formatted in their order.

    So if we have something like::

        {"one": "{two}", "two": "{three}", "three": 4}

    and we format ``"{one}"`` then, by the time we get to ``4``, the chain is
    ``["one", "two", "three"]``.

    This feature lets us raise an error if we have an option eventually
    formatting back to itself in a circle in our ``special_get_field``.

You'll notice that the difference between ``get_field`` in our first
implementation and this ``special_get_field`` is we now have access to the
``format_spec``. So if we format something like ``"{one:env}"`` then the value
is ``one`` and format_spec is ``env``.

Harpoon has the following implementation:

.. code-block:: python

    from harpoon.errors import BadOptionFormat

    from option_merge.formatter import MergedOptionStringFormatter
    from input_algorithms.meta import Meta

    class MergedOptionStringFormatter(MergedOptionStringFormatter):
        def get_string(self, key):
            """Get a string from all_options"""
            if key not in self.all_options:
                kwargs = {}
                if len(self.chain) > 1:
                    kwargs['source'] = Meta(self.all_options, self.chain[-2]).source
                raise BadOptionFormat("Can't find key in options", key=key, chain=self.chain, **kwargs)

            return super(MergedOptionStringFormatter, self).get_string(key)

        def special_get_field(self, value, args, kwargs, format_spec=None):
            """Also take the spec into account"""
            if format_spec in ("env", ):
                return value, ()

            if value in self.chain:
                raise BadOptionFormat("Recursive option", chain=self.chain + [value])

        def special_format_field(self, obj, format_spec):
            """Know about any special formats"""
            if format_spec == "env":
                return "${{{0}}}".format(obj)

This means we can do something like:

.. code-block:: python

    from harpoon.formatter import MergedOptionsStringFormatter
    from option_merge import MergedOptions
    options = MergedOptions()
    formatter = MergedOptionsStringFormatter(options, value="{blah:env}")
    print(formatter.format())
    # prints "${blah}"

Which is a handy way of generating variable interpolation for a bash command for
example.

We also have a ``formatted`` object from ``input_algorithms`` that we can
use instead of our implementation:

``option_spec/image_objs.py``

    .. code-block:: python

        from harpoon.formatter import MergedOptionsStringFormatter

        class Image(dictobj):
            [..]

        image_spec = sb.create_spec(Image
            , tag = sb.formatted(sb.string_spec(), formatter=MergedOptionsStringFormatter)
            , command = sb.defaulted(sb.formatted(sb.string_spec(), formatter=MergedOptionsStringFormatter), None)
            , commands = sb.listof(sb.string_spec())
            )

Which we can simplify a bit:

.. code-block:: python

    formatted_string = sb.formatted(sb.string_spec(), formatter=MergedOptionsStringFormatter)

    image_spec = sb.create_spec(Image
        , tag = formatted_string
        , command = sb.defaulted(formatted_string, None)
        , commands = sb.listof(sb.string_spec())
        )

Magical!

