.. _bh_s2_validating_input:

S2: Validating Input
====================

So far we've been relying on things ``just working™`` which isn't always the
case, so let's introduce some input validation with ``input_algorithms``.

First, add it to your ``setup.py``:

.. code-block:: python

    , install_requires =
      [ "input_algorithms==0.4.4.6"
      .....
      ]

And do another ``pip install -e .`` to make pip download and install it into
your virtualenv.

Now open up a Python interpreter and let's have a play around.

First, the setup, we need everything under ``input_algorithms.spec_base`` and
we need to make a ``meta`` object. I'll explain what this object does later on,
for now, just trust me that we need it::

    $ python
    > from input_algorithms import spec_base as sb
    > from input_algorithms.meta import Meta
    > meta = Meta({}, [])

And let's start validating things::

    > sb.string_spec().normalise(meta, "a_string")
    "a_string"

Awesome, the ``string_spec`` just retuns "a_string" because, well, it's a string!

Let's try something that isn't a string::

    > sb.string_spec().normalise(meta, 3)
    Traceback (most recent call last):
    File "<stdin>", line 1, in <module>
    File "/Users/stephen.moore/venv/harpoon/lib/python2.7/site-packages/input_algorithms/spec_base.py", line 47, in normalise
        return self.normalise_filled(meta, val)
    File "/Users/stephen.moore/venv/harpoon/lib/python2.7/site-packages/input_algorithms/spec_base.py", line 287, in normalise_filled
        raise BadSpecValue("Expected a string", meta=meta, got=type(val))
    input_algorithms.errors.BadSpecValue: "Bad value. Expected a string"    got=<type 'int'>        meta={source=<unknown>, path=}

Yay! 3 is not a string!

What about if we want a list of strings?::

    > sb.listof(sb.string_spec()).normalise(meta, ["one", "two"])
    ["one", "two"]

Yeap, that's good. Now what about a single string?::

    > sb.listof(sb.string_spec()).normalise(meta, "one")
    ["one"]

Woah! what?!¿! Why didn't it error?

Well this is why the method is called ``normalise`` and not just ``validate``.
``input_algorithms`` contains functions that return objects with a method called
``normalise``, which takes in a ``meta`` object and some piece of data to be
``normalised``. The object is named in such a way as to describe some specification
and will try it's best to turn the data into that specification or raise an
error.

Making your own input_algorithms
--------------------------------

Detour time! Let's make our own input_algorithms functions so you really
understand what is happening here.

Make a new file somewhere:

.. code-block:: python

    import six

    def manual_normalise(value):
        if type(value) is not list:
            raise Exception("Your value was not a list!")

        for index, thing in enumerate(value):
            if not isinstance(thing, six.string_types):
                raise Exception("The {0} value in the array was not a string!".format(index))

        return value

This function is fine, but it only validates, it doesn't normalise.
What if a string could be normalised to a list of one item?:

.. code-block:: python

    def manual_normalise(value):
        if isinstance(value, six.string_types):
            value = [value]

        if type(value) is not list:
            raise Exception("Your value was not a list!")

        for index, thing in enumerate(value):
            if not isinstance(thing, six.string_types):
                raise Exception("The {0} value in the array was not a string!")

        return value

    print(manual_normalise("hello"))
    # Prints '["hello"]' to the console

That's better, But now I also want to see all the values that aren't strings:

.. code-block:: python

    def manual_normalise(value):
        if isinstance(value, six.string_types):
            value = [value]

        if type(value) is not list:
            raise Exception("Your value was not a list!")

        failed = []
        for index, thing in enumerate(value):
            if not isinstance(thing, six.string_types):
                failed.append(index)

        if failed:
            raise Exception("There were values in the array that weren't strings!\tvalues={0}".format(failed))

        return value

    print(manual_normalise([1, 2, "three"])

And so on, with more details given to the errors.

What if we wanted a dictionary where each key is a string that matches a
particular regex and the values were a dictionary with particular keys where
some values are strings and some are booleans and some have defaults?

Suddenly our manual_normalise becomes really difficult to understand.

It's a bit easier when all you have to do is:

.. code-block:: python

    from input_algorithms import spec_base as sb
    from input_algorithms.meta import Meta
    meta = Meta({}, [])
    spec = sb.listof(sb.string_spec())

    print(spec.normalise(meta, "one"))

So, onto our hypothetical complex scenario, Let's define an object first:

.. code-block:: python

    class Something(object):
        def __init__(self, one, two, three):
            self.one = one
            self.two = two
            self.three = three

Now say we want a dictionary where all the keys have are alphanumerical
with atleast one underscore:

.. code-block:: python

    from input_algorithms.validators import Validator
    import re

    class ValidKey(Validator):
        def validate(self, meta, val):
            matcher = re.compile("^[a-zA-Z0-9]+_[a-zA-Z9-9_]+$")
            if not matcher.match(val):
                raise Exception("Our value does not match the pattern!\twanted={0}\tpattern={1}".format(val, matcher.pattern))
            return val

This class can be used to normalise a string:

.. code-block:: python

    ValidKey().normalise(Meta({}, []), "hello")
    # Raises an exception!

Let's put it all together:

.. code-block:: python

    complex_spec = sb.dictof(
          sb.valid_string_spec(ValidKey())
        , sb.create_spec(Something
            , one = sb.required(sb.string_spec())
            , two = sb.defaulted(sb.boolean(), False)
            , three = sb.integer_spec()
            )
        )

    result = complex_spec.normalise(meta, {"stuff_and_things": {"one": "yeap", "two": True, "three": 89}})
    print("-" * 80)
    print(type(result))
    print(result["stuff_and_things"].one)

    print("-" * 80)
    try:
        complex_spec.normalise(meta, {"five": 5})
    except Exception as error:
        print(error)

    print("-" * 80)
    complex_spec.normalise(meta, {"trees_wonderful": {"two": 5, "three": "t"}})

If you have been following along and have that all in a file you should see
something like the following::

    --------------------------------------------------------------------------------
    <type 'dict'>
    yeap
    --------------------------------------------------------------------------------
    Our value does not match the pattern!   wanted=five     pattern=^[a-zA-Z0-9]+_[a-zA-Z9-9_]+$
    --------------------------------------------------------------------------------
    Traceback (most recent call last):
    File "blah.py", line 43, in <module>
        complex_spec.normalise(meta, {"trees_wonderful": {"two": 5, "three": "t"}})
    File "/Users/stephen.moore/deleteme/ownharpoon/venv/lib/python2.7/site-packages/input_algorithms/spec_base.py", line 50, in normalise
        return self.normalise_filled(meta, val)
    File "/Users/stephen.moore/deleteme/ownharpoon/venv/lib/python2.7/site-packages/input_algorithms/spec_base.py", line 113, in normalise_filled
        raise BadSpecValue(meta=meta, _errors=errors)
    input_algorithms.errors.BadSpecValue: "Bad value"       meta={source=<unknown>, path=}
    errors:
    =======

            "Bad value"     meta={source=<unknown>, path=trees_wonderful}
            errors:
            =======

                    "Bad value. Expected a value but got none"      meta={source=<unknown>, path=trees_wonderful.one}
            -------
                    "Bad value. Expected an integer"        got=<type 'str'>        meta={source=<unknown>, path=trees_wonderful.three}
            -------
                    "Bad value. Expected a boolean" got=<type 'int'>        meta={source=<unknown>, path=trees_wonderful.two}
            -------
    -------

It shows us that from a relatively simple specification we can detailed
information when something isn't right.

Using input_algorithms
----------------------

Ok, now it's time to understand the ``meta`` object. This is an object that
is passed around by ``input_algorithms`` logic that represents the complete
configuration in question and where in the configuration we are at. That's how
the error is able to tell you the ``source`` and ``path`` information of where
each error is at.

So let's validate the input for our Image object, first inside ``image_objs.py``:

.. code-block:: python

    from input_algorithms import spec_base as sb

    class Image(object):
        [..]

    image_spec = sb.create_spec(Image
        , tag = sb.string_spec()
        , commands = sb.listof(sb.string_spec())
        )

.. code-block:: python

    from harpoon.option_spec.image_objs import image_spec

    from input_algorithms.meta import Meta

    class Collector(object):
        [..]

        def start(self, args_dict):
            meta = Meta(self.configuration, [])
            self.configuration["image"] = image_spec.normalise(meta, self.configuration)

            chosen_task = self.configuration["harpoon"]["task"]
            available_actions[chosen_task](self, args_dict)

Now put bad data in your config and run ``harpoon build_and_run``.

You should notice two things now. Firstly extra data in the configuration gets
ignored and not passed into the Image constructor. Secondly anything not matching
the specification for ``tag`` and ``command`` produces errors.

Another thing to note is that ``source`` in the errors is still set to
"<unknown>", this will be solved with ``option_merge`` in the next module.

Finally we'll also see that it fails validating image even if we just want to
list tasks. This will also be solved by ``option_merge`` when we make it lazily
normalise the image configuration.

