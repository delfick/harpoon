.. _bh_s3_context:

S3: The Context
===============

Ok, let's have a break from the config and do something constructive.

If you remember all the way back to section1 I mentioned that docker is a
server-client architecture. This means that the server, the thing doing all
the work, doesn't know where the client is calling it from.

The implication of this is that any files we add into the image must be
explicitly passed to the server before they can be added to the image.

Collecting files
----------------

Before we can make a tar file we must first know what we're putting into it.

Let's start with the easy part: The configuration!

``config.yml``:

    .. code-block:: yaml

        ---

        tag_prefix: local

        images:
            cloc:
                context:
                    parent_dir: "{config_root}/harpoon"

                tag: "{tag_prefix}/{_key_name_1}"

                commands:
                    - FROM ubuntu:14.04
                    - ADD . /project
                    - RUN sudo apt-get update && apt-get install -y cloc
                    - CMD cloc /project

            mine:
                context: false

                [..]

Now what I've done here is define the context in two different ways. For the
``cloc`` image I've defined ``context`` as a dictionary of options, whereas I've
defined it as a boolean for the ``mine`` image.

``input_algorithms`` has a helper for this kind of definition where we convert
the boolean into a dictionary with a particular option set:

``option_spec/image_objs.py``

    .. code-block:: python

        class Context(dictobj):
            fields = ["enabled", "parent_dir"]

        class Image(dictobj):
            fields = ["tag", "context", "command", "commands"]

            [..]

        def context_spec():
            """Spec for specifying context options"""
            return sb.dict_from_bool_spec(lambda meta, val: {"enabled": val}
                , sb.create_spec(Context
                    , enabled = sb.defaulted(sb.boolean(), True)
                    , parent_dir = sb.formatted(sb.defaulted(sb.string_spec(), "{config_root}"), formatter=MergedOptionStringFormatter)
                    )
                )

        formatted_string = sb.formatted(sb.string_spec(), formatter=MergedOptionsStringFormatter)

        image_spec = sb.create_spec(Image
            , tag = formatted_string
            , context = context_spec()
            , command = sb.defaulted(formatted_string, None)
            , commands = sb.listof(sb.string_spec())
            )

We can do a little bit better as well and validate that ``parent_dir`` is indeed
a directory that exists by using ``sb.directory_spec``:

.. code-block:: python

    , create_spec(Context
        , enabled = sb.defaulted(sb.boolean(), True)
        , parent_dir = sb.directory_spec(sb.formatted(sb.defaulted(string_spec, "{config_root}"), formatter=MergedOptionStringFormatter))
        )
    )

Ok, now we know the parent directory to add our files from, let's make an iterator
that will return all of files under there:

``ship/context.py``

    .. code-block:: python

        import os

        class ContextBuilder(object):

            def find_files(self, parent_dir):
                for root, dirs, files in os.walk(parent_dir):
                    for filename in files:
                        location = os.path.join(root, filename)
                        yield location, os.path.relpath(location, parent_dir)

.. note:: We're creating a new python module now called ``ship`` which means we
    need to also create ``ship/__init__.py``

Before we string the two together and construct our tarfile, we'll take one more
detour and define yet another file:

``helpers.py``

    .. code-block:: python

        from contextlib import contextmanager
        import tempfile
        import os

        @contextmanager
        def a_temp_file():
            """Yield the name of a temporary file and ensure it's removed after use"""
            filename = None
            try:
                tmpfile = tempfile.NamedTemporaryFile(delete=False)
                filename = tmpfile.name
                yield tmpfile
            finally:
                if filename and os.path.exists(filename):
                    os.remove(filename)

This is a helper that we can use to create a temporary file, usage looks like:

.. code-block:: python

    from harpoon.helpers import a_temp_file

    with a_temp_file() as fle:
        fle.write("hello there")
        fle.flush()
        fle.seek(0)

        print(fle.read())
        # Prints "hello there"

        print(fle.name)
        # Prints the location of the file

    print(os.path.exists(fle.name))
    # Prints False, because the file is cleaned up now that we're
    # outside of the with block

Making the tar file
-------------------

So let's add a method to our ``ContextBuilder`` class that will build our tar
file.

``ship/context.py``:

    .. code-block:: python

        from harpoon import helpers as hp

        from contextlib import contextmanager
        import tarfile

        class ContextBuilder(object):
            [..]

            @contextmanager
            def make_context(self, context):
                with hp.a_temp_file() as f
                    t = tarfile.open(mode="w:gz", fileobj=f)
                    if context.enabled:
                        for filename, arcname in self.find_files(context.parent_dir):
                            t.add(filename, arcname)

                    yield (t, f)

Secondly, let's convert our existing ``dockerfile`` method on ``Image`` to use
our new ``a_temp_file``:

``option_spec/image_objs.py``

    .. code-block:: python

        from harpoon import helpers as hp

        from contextlib import contextmanager

        class Image(dictobj):
            [..]

            @contextmanager
            def dockerfile(self):
                with hp.a_temp_file() as fle:
                    fle.write("\n".join(self.commands))
                    fle.flush()
                    fle.seek(0)
                    yield fle

Now, we're ready to use our ``ContextBuilder``.

``option_spec/image_objs.py``

    .. code-block:: python

        from harpoon.ship.context import ContextBuilder

        class Image(dictobj):

            [..]

            @contextmanager
            def the_context(self):
                with ContextBuilder().make_context(self.context) as (t, f):
                    with self.dockerfile() as dockerfile:
                        t.add(dockerfile.name, "./Dockerfile")

                    yield (t, f)

            def build(self, harpoon):
                [..]

                try:
                    with self.the_context() as (t, f):
                        #
                        # Important! The tarfile must be closed before it can be used!
                        #
                        t.close()
                        f.flush()
                        f.seek(0)
                        for line in client.build(fileobj=f, custom_context=True, rm=True, tag=self.tag, pull=False):
                            print(line)
                except docker.errors.APIError as error:
                    [..]

Now run ``harpoon build_and_run cloc``

.. note:: If you get it complaining that ``TypeError: __init__() got an unexpected keyword argument 'context'``
  then you forgot to add ``context`` to the fields for ``Image``.

Refactor
--------

This works! But it's a bit messy. We're passing around tuples and doing multiple
actions on both items in those tuples.

Let's instead pass around an object that encapsulates all this:

``ship/context.py``

    .. code-block:: python

        class ContextWrapper(object):
            def __init__(self, tarfile, fileobj):
                self.tarfile = tarfile
                self.fileobj = fileobj

            def close(self):
                self.tarfile.close()
                self.fileobj.flush()
                self.fileobj.seek(0)

        class ContextBuilder(object):

            @contextmanager
            def make_context(self, context):
                with hp.a_temp_file() as f
                    t = tarfile.open(mode="w:gz", fileobj=f)
                    [..]
                    yield ContextWrapper(t, f)

``option_spec/image_objs.py``

    .. code-block:: python

        class Image(dictobj):
            [..]

            @contextmanager
            def the_context(self):
                with ContextBuilder().make_context(self.context) as context:
                    with self.dockerfile() as dockerfile:
                        context.tarfile.add(dockerfile.name, arcname="./Dockerfile")
                    yield context

            def build(self, harpoon):
                [..]

                try:
                    with self.the_context() as context:
                        # Must close the context before sending it to the docker daemon
                        context.close()
                        for line in client.build(fileobj=context.fileobj, custom_context=True, rm=True, tag=self.tag, pull=False):
                            print(line)
                except docker.errors.APIError as error:
                    [..]

The docker cache
----------------

If you're curious enough you may have run ``harpoon build_and_run cloc`` multiple
times and noticed that it doesn't seem to respect your docker cache anymore and
keeps rebuilding (try it if you haven't!).

This is because our Dockerfile is a new temporary file each time which has a
different modified time every time we run the code.

In the real harpoon we give the Dockerfile the same modified time as the config
file, but for the sake of simplicity, we'll just give it a modified time of 0:

``option_spec/image_objs.py``

    .. code-block:: python

        import os

        class Image(dictobj):
            [..]

            @contextmanager
            def dockerfile(self):
                with hp.a_temp_file() as fle:
                    fle.write("\n".join(self.commands))
                    fle.flush()
                    fle.seek(0)
                    os.utime(fle.name, (0, 0))
                    yield fle

Now when you run ``harpoon build_and_run cloc`` multiple times, the cache will
be remembered!

.. note:: The better way would be to add the context after we do the apt-get
  install, but I've done it this way round to make the lack of cache noticeable!

Recap
-----

* We have context options on our Image object
* We have a ContextBuilder that makes a tarfile using those options
* The ContextBuilder returns a ContextWrapper that encapsulates the tarfile and
  the underlying file object for that tarfile.
* The Image object adds a Dockerfile to the tarfile
* The Image closes the context and then throws it at the docker daemon
* The docker daemon sees the ``ADD . /harpoon`` line in the Dockerfile and adds
  everything from the context into ``/harpoon`` in the image

In the next module, we're gonna implement the ability to inherit from images!
