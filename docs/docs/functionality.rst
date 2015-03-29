.. _functionality:

Functionality
=============

Harpoon comes with a fair amount of functionality.

Failed build intervention
-------------------------

Harpoon has the ability to commit failed images during build and run ``/bin/bash``
against this image. This behaviour is known as ``intervention``.

Intervention images are cleaned up after they are exited from and are disabled
if harpoon is run with either ``--non-interactive`` or with ``--no-intervention``.

The yaml configuration
----------------------

Harpoon reads everything from a yaml configuration. By default this is a
``harpoon.yml`` file in the current directory, but may be changed with the
``--harpoon-config`` option or ``HARPOON_CONFIG`` environment variable.

It will also read from ``~/.harpoon.yml`` and will be overridden by anything in
the configuration file you've specified.

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
      - RUN apt-get update && apt-get -y install caca-utils
      - CMD cacafire

And then we can do things like::

  # Run the default command in the image
  $ harpoon run myapp

  # Make the image and start an interactive bash shell in it
  $ harpoon ssh myapp

And harpoon will make sure things are cleaned up and no longer on your system
when you quit the process.

The only required option for an image is ``commands`` which is a list of commands
as what you would have in a Dockerfile.

Modified file times
-------------------

We noticed that if you git clone a repository then git will set the modified
times of all the files to the time at which you do the git clone.

This means that even though the file contents are the same, docker will invalidate
the cache when it adds these files.

Harpoon provides an option ``context.use_git_timestamps`` which when set true will use
git to determine the commit date for each file and when it creates the context to
send to docker it will use the git date.

for example::

  ---

  context:
    use_git_timestamps: true

  images:
    blah:
      commands:
        [...]

It will make sure to only do this to files that are controlled by git and which
don't have any local modifications

Note that if you have many files, you might decide that getting the commit date
for all of them takes an unacceptably long time and that you only care about a
certain subset of files.

In this case, you may specify a list of globs that will be used to identify which
files we set the modified times for (assuming they are also owned by git and don't
have any local modifications.

For example::

  ---

  context:
    use_git_timestamps:
      - gradle*
      - settings.gradle
      - buildSrc/**

  images:
    blah:
      commands:
        [...]

Controlling the context
-----------------------

Docker is a server-client architecture, where the server is essentially a web
server that speaks HTTP.

When you build an image with a docker client (for example
the official docker cli tool), the client must first send a ``context`` to the
server. This context is then used to locate files that are added to the image
via `ADD <https://docs.docker.com/reference/builder/#add>`_ commands.

Harpoon has options available for specifying what goes into the context uploaded
to the docker server. For now, it's a little limited, but it's certainly better
than no control.

These options may be specified either at the root of the configuration or within
the options for the image itself. Any option in the image options overrides the
root option.

use_gitignore
  Ignore anything gitignore would when creating the context.

exclude
  A list of globs that are used to exclude files from the context

  Note: Only works when use_gitignore has been specified

enabled
  Don't include any context from the local system if this is set to false.

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

  context:
    use_gitignore: true

  folders:
    - project_dir: "{config_root}/.."

  images:
    myapp:
      context:
        parent_dir: "{folders.project_dir}"
        exclude:
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
          - ["{images.db}", "dbhost"]

        commands:
          - <commands here>

The formatting works such that looking for "{name}" will look for ``name`` in the
options. In this case it looks for 'options["images"]["db"]["container_name"]'

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
          options:
            bash: "echo {THINGS:env} > /tmp"
            env:
              - THINGS

Then this will run the container with the docker-cli equivalent of "--env THINGS"
and run the command "/bin/bash -c 'echo ${THINGS} > /tmp'".

You can also specify environment variables via the --env switch.

Also, you can specify "env", "images.<image>.env" or
"images.<image>.tasks.<task>.env" as a list of environment variables you want
in your image.

The syntax for the variables are:

  VARIABLE
    Will complain if this variable isn't in your current environment and will
    expose this environment variable to the container

  VARIABLE=VALUE
    Will set this variable to VALUE regardless of whether it's in your environment
    or not

  VARIABLE:DEFAULT
    Will set this variable to DEFAULT if it's not in your current environment,
    otherwise it will use the value in your environment

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

  The first string is used as is, the second string is formatted and the two
  results are joined together to form the command.

  So let's say you have::

    ---

    image_name_prefix: amazing-project

    images:
      base:
        commands:
          <commands here>
      app:
        commands:
          - [FROM, "{images.base}"]

  Then the first instruction for the ``app`` Dockerfile will be a FROM command
  that uses the ``base`` image.

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
      context:
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
      context:
        parent_dir: "{folders.api_dir}"

      commands:
        - [FROM, "{images.bundled}"]
        - VOLUME shared

        <install mysql>

        ## Expose the database
        - EXPOSE 3306

        - [ADD, {prefix: "/app", get: ["db", "lib", "config", "app", "Rakefile"]}]

        ## Run the migrations
        - RUN (mysqld &) && rake db:create db:migrate

        - CMD cp /app/db/schema.rb /shared && mysqld

    unit_tests:
      context:
        parent_dir: "{folders.api_dir}"

      link:
        - ["{images.mysql}", "dbhost"]

      volumes:
        share_with:
          - "{images.mysql}"

      commands:
        - [FROM, "{images.bundled}"]
        - ADD . /app/

        - CMD cp /shared/schema.rb /app/db && rake

And harpoon will ensure that the bundled image is created before both the mysql
and unit_tests images are created, and that when we run the unit_tests container
it first creates the mysql container.

Harpoon will also ensure all these containers are cleaned up afterwards. Images
stay around because we want to use the awesome caching powers of Docker.

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
          - ["{images.db.container_name}", "dbhost"]
        commands:
          ...

  Will make sure that when you start the app container, it will run the db
  image in a detached state and there will be an entry in the ``/etc/hosts`` of
  the ``app`` container that points ``dbhost`` to this ``db`` container.

volumes.share_with
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
        volumes:
          share_with:
            - "{images.db}"
        commands:
          ...

  Then the ``app`` container will share the volumes from the ``db`` container.

volumes.mount
  This is also specified as string similar to what you do for the docker cli
  (https://docs.docker.com/userguide/dockervolumes/#data-volumes)

  For example::

    ---

    folders:
      app_dir: "{config_root}/../app"

    images:
      app:
        volumes:
          mount:
            - "{app_dir}/coverage:/project/app/coverage:rw"

  Will mount the ``coverage`` directory from the host into /project/app/coverage
  on the image.

Sometimes you need your dependency container to not be running in a detached
container. To make it so a dependency is running in an attached container, you
may specify ``dependency_options``::

  ---

  images:
    runner:
      commands:
        ...
        - CMD activator run

    uitest:
      link:
        - ["{images.runner}", "running"]

      dependency_options:
        runner:
          # Typesafe activator run stops in a detached container
          attached: True

      commands:
        ...
        - CMD ./do_a_uitest.sh running:9000
