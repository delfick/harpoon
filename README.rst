Harpoon
=======

An opinionated wrapper around the docker-py API to docker that knows how to read
yaml files and make things happen.

Installation
------------

Just use pip::

  pip install docker-harpoon

Usage
-----

Once harpoon is installed, there will be a new program called ``harpoon``.

When you call harpoon without any arguments it will print out the tasks you
have available.

You may invoke these tasks with the ``task`` option.

The default tasks are as follows:

ssh
  Takes in an --image option and make the specified image and run /bin/bash
  with it

run
  Takes in an --image option and either ``--command <command>`` or
  ``--bash <bash>``. It will create the image you specified and run it with
  either ``<command>`` or ``/bin/bash -c '<bash>'`` depending on what you
  specified

  You can also specify environment options with --env. These options are similar
  to what docker cli asks for. (https://docs.docker.com/reference/commandline/cli/
  search for "--env")

make
  Takes in an --image option and will make that image

push
  Takes in an --image option, creates your specified image and pushes it

list_tasks
  This is the default task, it will print out what tasks are available.

  Including these default tasks and any custom tasks you have defined.

delete_untagged
  This will find the untagged images and delete them.

Note that when harpoon creates an image, it will also create the dependent
images that are defined in the configuration.

Also, by default when an image becomes untagged because a new one that harpoon
creates takes the ``latest`` tag, it will be deleted. This behaviour is
prevented with the ``--keep-replaced`` option.

Simpler Usage
-------------

I found out after a while that, in my usage atleast, ``--task`` and ``--image``
are specified a lot and are annoying to type so if the first positional argument
doesn't start with a ``-`` it is taken as the ``task`` and if the seecond
positional argument doesn't start with a ``-`` it is taken as the image.

So::

    $ harpoon --task run --image my_amazing_image

Is equivalent to::

    $ harpoon run my_amazing_image

Failed build intervention
-------------------------

I noticed when you're trying to work out what commands to put in your Dockerfile
it helps to docker commit the last image that was created and run /bin/bash in
the resulting image.

The problem with this is you have to remember to keep clearing away these
images and containers otherwise you'll run out of disk space after a while.

So I've added behaviour to harpoon such that when it fails a build it will ask
if you want to make an "intervention image" and follow this pattern.

It will also cleanup everything after you're done.

This behaviour is disabled if harpoon is run with --non-interactive or
--no-intervention.

The yaml configuration
----------------------

Harpoon reads everything from a yaml configuration. By default this is a
``harpoon.yml`` file in the current directory, but may be changed with the
--harpoon-config option.

This yaml file looks like the following::

  ---

  images:
    <image_name>:
      <image_options>

And so when harpoon reads this yaml, it gets a dictionary of images names to
image options under the ``images`` key.

An example may look like the following::

  ---

  images:
  myapp:
    commands:
      - FROM ubuntu
      - RUN sudo apt-get -y install caca-utils
      - CMD cacafire

And then we can do things like::

  # Run the default command in the image
  $ harpoon --task run --image myapp

  # Make the image and start an interactive bash shell in it
  $ harpoon --task ssh --image myapp

And harpoon will make sure things are cleaned up and no longer on your system
when you quit the process.

The minimum you need in the options is the commands to be run in a Dockerfile.

If you supply a string, that string will be placed as is in the Dockerfile that
we end up creating the image from. See https://docs.docker.com/reference/builder/
for what commands are available in docker files.

Controlling the context
-----------------------

Docker is a server-client architecture, where the server is essentially a web
server that speaks HTTP. When you build an image with a docker client (for example
the official docker cli tool), the client must first send a ``context`` to the
server. This context is then used to locate files that are added to the image
via `ADD <https://docs.docker.com/reference/builder/#add>`_ commands.

Harpoon has options available for specifying what goes into the context uploaded
to the docker server. For now, it's a little limited, but it's certainly better
than no control.

These options may be specified either at the root of the configuration or within
the options for the image itself. Any option in the image options overrides the
root option.

respect_gitignore
  Ignore anything gitignore would when creating the context.

context_exclude
  A list of globs that are used to exclude files from the context

  Note: Only works when respect_gitignore has been specified

no_host_context
  Only include the Dockerfile and any inline ADD files.

parent_dir
  The parent directory to get the context from. This defaults to the folder the
  ``harpoon.yml`` was found in.

For example, let's say you have the following file structure::

  project/
    app/
    ui-stuff/
    large_folder/
    docker/
      harpoon.yml

Where for some reason large_folder is committed into git but contains a lot of
large assets that don't need to be in the docker image, then the harpoon.yml
may look something like::

  ---

  respect_gitignore: true

  folders:
    - project_dir: "{config_root}/.."

  images:
    myapp:
      parent_dir: "{folders.project_dir}"
      context_exclude:
        - large_folder/**
        - docker/**

      commands:
        - FROM ubuntu
        - ADD app /project/app
        - ADD ui-stuff /project/ui-stuff
        - RUN setup_commands

This also means it's very easy to have multiple docker files adding content from
the same folder.

Inter-Document linking
----------------------

Many option values in the ``harpoon.yml`` file will be formatted such that you
can reference the value from something else in the document.

For example, let's say you want to link one image into another::

    ---

    images:
      db:
        commands:
          - <commands here>
      app:
        link:
          - "{images.db.container_name}:dbhost"

        commands:
          - <commands here>

The formatting works by looking for "{name}" and will look for ``name`` in the
options. So in this case it looks for 'options["images"]["db"]["container_name"]'

Note that images have some generated values:

image_name
  The name of the image that is created. This is produced by concatenating the
  ``image_index`` and ``image_name_prefix`` options it finds with the name of
  the image.

  So for::

    ---

    image_index: some-registry.somewhere.com/user/
    image_name_prefix: my-project
    images:
        blah:
            [..]

  ``images.blah.image_name`` will be "some-registry.somewhere.com/user/my-project-blah"

container_name
  This is a concatenation of the ``image_name`` and a uuid1 hash.

  This means if we fail to clean up, future invocations won't complain about
  conflicting container names.

Note that this means image names can't have dots in them, because the formatter
will split the name of the image by the dots and it won't do what you expect.

Environment variables
---------------------

There is a special format ":env" that you can use to transform something into
a bash variable.

For example::

  ---

  images:
    blah:
      commands:
        ...

      tasks:
        something:
          - run_task
          - []
          - bash: "echo {THINGS:env} > /tmp"
            env:
              - THINGS

Then this will run the container with the docker-cli equivalent of "--env THINGS"
and run the command "/bin/bash -c 'echo ${THINGS} > /tmp'".

This is a thing I've implemented because yaml doesn't seem to like
escaped brackets.

You can also specify environment variables via the --env switch.

Also, you can specify "harpoon.env" as a list at the root of the configuration
or in the configuration for each image.

Dockerfile commands
-------------------

So when you specify your image you specify a list of commands to go into the
Dockerfile as a list of instructions::

  ---

  images:
    myimage:
      commands:
        - <instruction>
        - <instruction>
        - <instruction>

Where instruction may be::

<string>

  A string is just added into the Dockerfile as is

[<string>, <string>]

  Translates into [<string>, [<string>]]

  So let's say you have::

    ---

    image_name_prefix: amazing-project

    images:
      base:
        commands:
          <commands here>
      app:
        commands:
          - [FROM, "{images.base.image_name}"]

  Then the first instruction for the ``app`` Dockerfile will be
  "FROM amazing-project-base"

[<string>, [<string>, <string>, ...]]
  A list of a string and a list will use the first string as the command
  unmodified and it will then format each string and use that as a seperate
  value.

  So let's say you have::

    ---

    image_name_prefix: amazing-project

    passwords:
      db: sup3rs3cr3t

    images:
      app:
        commands:
          - FROM ubuntu
          - [ENV, ["DBPASSWORD {passwords.db}", "random_variable 3"]]

  Then the resulting Dockerfile for the ``app`` image will look like::

    FROM ubuntu
    ENV DBPASSWORD sup3rs3cr3t
    ENV random_variable 3

[<string>, <dictionary>]
  This has special meaning depending on the first String.

  [ADD, {content:<content>, dest:<dest>}]

    This will add a file to the context with the content specified and make
    sure that gets to the destination specified.

    So say you have::

      ---

      images:
        app:
          commands:
            - FROM ubuntu
            - - ADD
              - dest: /tmp/blah
                content: |
                  blah and
                  stuff

    This will add a file to the context with the name as some uuid value.
    For example "DDC895F6-6F65-43C1-BDAA-00C4B3F9BB7B" and then the
    Dockerfile will look like::

      FROM ubuntu
      ADD DDC895F6-6F65-43C1-BDAA-00C4B3F9BB7B /tmp/blah

  [ADD, {prefix: <prefix>, get:[<string>, <string>]}]

    This is a shortcut for adding many files with the same destination
    prefix.

    For example::

      ---

      images:
        app:
          commands:
            - FROM ubuntu
            - - ADD
              - prefix: /app
                get:
                  - app
                  - lib
                  - spec

    Which translates to::

      FROM ubuntu
      ADD app /app/app
      ADD lib /app/lib
      ADD spec /app/spec

Dependant containers
--------------------

When you reference an image_name created by the harpoon config, then harpoon
will ensure that image is created before it's used.

Also, if you specify a container_name created by the harpoon config, harpoon
will ensure that container is running before it is used.

For example, say you have this folder structure::

  project/
    app/
      app/
      db/
      lib/
      spec/
      config/
      Gemfile
      Gemfile.lock
      Rakefile
    docker/
      harpoon.yml

Then your harpoon.yml may look like::

  ---

  folders:
    api_dir: "{config_dir}/.."

  images:
    bundled:
      parent_dir: "{folders.api_dir}"

      commands:
        - FROM some_image_with_ruby_installed

        - RUN apt-get -y install libmysqlclient-dev ruby-dev

        - RUN mkdir /api
        - ADD Gemfile /api/
        - ADD Gemfile.lock /api/

        - WORKDIR /api
        - RUN bundle config --delete path && bundle config --delete without && bundle install

    mysql:
      parent_dir: "{folders.api_dir}"

      commands:
        - [FROM, "{images.bundled.image_name}"]
        - VOLUME shared

        <install mysql>

        ## Expose the database
        - EXPOSE 3306

        - [ADD, {prefix: "/app", get: ["db", "lib", "config", "app", "Rakefile"]}]

        ## Run the migrations
        - RUN (mysqld &) && rake db:create db:migrate

        ## It would appear docker cp does not work on macs :(
        ## Hence we copy the schema.rb into /shared for distribution via that
        - CMD cp /app/db/schema.rb /shared && mysqld

    unit_tests:
      parent_dir: "{folders.api_dir}"

      link:
        - "{images.mysql.container_name}:dbhost"

      volumes_from:
        - "{images.mysql.container_name}"

      commands:
        - [FROM, "{images.bundled.image_name}"]
        - ADD . /app/

        - CMD cp /shared/schema.rb /app/db && rake

And harpoon will ensure that the bundled image is created before both the mysql
and unit_tests images are created, and that when we run the unit_tests container
it first creates the mysql container.

Harpoon will also ensure all these containers are cleaned up afterwards. Images
stay around because we want to use the awesome caching powers of Docker.

Custom tasks
------------

You can add tasks within your container.

For example::

  ---

  images:
    app:
      commands:
        ...
        - CMD startup_app

      tasks:
        run_app:
          spec: run_task
          description: "Startup the app"

        run_tests:
          spec:
            - run_task
            - []
            - bash: cd /app && rake tests
          description: Run the unit tests

Each task needs a ``spec`` and can be given an optional ``description``.

If the spec is just a string, then it will call that task and give the ``image``
option as the name of this image.

If the spec is a list, then it is (task_name, args, kwargs) and the python code
will just do a ``task_name(*args, **kwargs)``.

The available tasks are defined in ``harpoon.tasks`` and are push, make, run_task
and list_tasks.

The tasks defined in these definitions will be shown when you do
"harpoon --task list_tasks".

You may also specify extra options for your tasks::

  ---

  images:
    app:
      commands:
        ...
      tasks:
        something:
          spec:
            - run_task
            - []
            - bash: cd /app && ./some_script.sh {$@}

Then say you run harpoon like::

  $ harpoon --task something -- --an-option 1

Then it will start up the app container and run::

  $ /bin/bash -c 'cd /app && ./some_script.sh --an-option 1'

Because everything that comes after a ``--`` in the argv to harpoon will be
available as "$@".

Linking containers and volumes
------------------------------

You have the following options available:

link
  A list of strings that are equivalent to the options you give link for
  docker cli (https://docs.docker.com/userguide/dockerlinks/#container-linking)

  For example::

    ---

    images:
      db:
        commands:
          ...
      app:
        link:
          - "{images.db.container_name}:dbhost"
        commands:
          ...

  Will make sure that when you start the app container, it will run the db
  image in a detached state and there will be an entry in the ``/etc/hosts`` of
  the ``app`` container that points ``dbhost`` to this ``db`` container.

volumes_from
  This behaves like ``link`` in that you specify strings similar to what you
  would do for the docker cli (https://docs.docker.com/userguide/dockervolumes/#creating-and-mounting-a-data-volume-container)

  So something like::

    ---

    images:
      db:
        commands:
          - FROM ubuntu
          - VOLUME /shared
      app:
        volumes_from:
          - "{images.db.container_name}"
        commands:
          ...

  Then the ``app`` container will share the volumes from the ``db`` container.

volumes
  This is also specified as string similar to what you do for the docker cli
  (https://docs.docker.com/userguide/dockervolumes/#data-volumes)

  For example::

    ---

    folders:
      app_dir: "{config_root}/../app"

    images:
      app:
        volumes:
          - "{app_dir}/coverage:/project/app/coverage:rw"

  Will mount the ``coverage`` directory from the host into /project/app/coverage
  on the image.

Roadmap
-------

There are two immediate things on the roadmap:

* Clean up imager.py
* Write automated tests

The second task is self describing.

The first task is because imager.py handles too much. It does:

* Configuration collection, interpretation and validation
* Ordering of dependency containers
* Knows how to use dockerpy
* Knows how to interpret dockerpy output

Additionally to that, the configuration has multiple sources (cli, task definiton,
root of the config, image config) and it arbitrarily gets certain values from
certain combinations of that.

The next evolution of imager.py will split out these different concerns, as well
as use `OptionMerge <https://github.com/delfick/option_merge>`_ a bit better
so when I get options for the image, these different sources are already merged.

Tests
-----

Run the helpful script::

  ./test.sh

Note that I essentially have no automated tests.

