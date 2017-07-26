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
        links:
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

  [ADD, {content:<content>, mtime:<mtime>, dest:<dest>}]

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
                mtime: 1433139432
                content: |
                  blah and
                  stuff

    This will add a file to the context with the name as some uuid value.
    For example "DDC895F6-6F65-43C1-BDAA-00C4B3F9BB7B" and then the
    Dockerfile will look like::

      FROM ubuntu
      ADD DDC895F6-6F65-43C1-BDAA-00C4B3F9BB7B /tmp/blah

    The mtime you specify will be the modified time that is given to this temp
    file.

  [ADD, {content: {image: <image>, path: <path>}, dest: <dest>, mtime: <mtime>}]

    This will add the files found in <image> at <path> to <dest>. It uses a tar
    file to add in these files to the context and that tar file with have a
    modified time of <mtime>

    For example:

    .. code-block:: yaml

      ---

      images:
        one:
          commands:
            - FROM busybox
            - RUN mkdir /tmp/blah
            - RUN echo 'lol' > /tmp/blah/one
            - RUN echo 'hehehe' > /tmp/blah/two
            - RUN mkdir /tmp/blah/another
            - RUN echo 'hahahha' > /tmp/blah/another/three
            - RUN echo 'hello' > /tmp/other

        two:
          commands:
            - FROM busybox

            - - ADD
              - dest: /tmp/copied
                content:
                  image: "{images.one}"
                  path: /tmp/blah
                mtime: 1463473251

            - - ADD
              - dest: /tmp/copied/other
                content:
                  image: "{images.one}"
                  path: /tmp/other
                mtime: 1463473251

            - CMD find /tmp/copied -type f -exec echo {} \; -exec cat {} \;

          tasks:
            cat:
              description: Cat out the copied file from the one image!

    Using this definition, we can now run ``harpoon cat`` and it will print out
    the files we stole from the ``one`` image!

  [ADD, {context:<context>, mtime:<mtime>, dest:<dest>}]

    This is the same as specifying ``content`` instead of ``context``, however
    ``context`` is the same as the context options on the image and will create
    a tar archive that is untarred into the dockerfile.

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

      links:
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

links
  A list of strings representing the container name to link into the container

  Or a list of list of strings of ``[container_name, link_name]`` where
  ``container_name`` may be of the form ``{images.<image_name>}`` (i.e. a
  reference to an image specified in the configuration.

  Harpoon will spawn docker networks such that each container has it's own
  network with the specified linked containers in it.

  These networks are cleaned up when all the containers specified in it have
  been stopped.

  For example::

    ---

    images:
      db:
        commands:
          ...
      app:
        links:
          - ["{images.db}", "dbhost"]
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
      links:
        - ["{images.runner}", "running"]

      dependency_options:
        runner:
          # Typesafe activator run stops in a detached container
          attached: True

      commands:
        ...
        - CMD ./do_a_uitest.sh running:9000

Waiting for dependency containers
---------------------------------

Harpoon will let you specify ``wait_condition`` options to say what conditions
must be satisfied before a container is considered ready to be used as a
dependency.

For example:

.. code-block:: yaml

  ---

  images:
    first:
      commands:
        - FROM ubuntu:14.04
        - CMD sleep 4 && touch /tmp/wait

      wait_condition:
        file_exists:
          - /tmp/wait

    second:
      links:
        - "{image.first}"

      commands:
        - FROM ubuntu:14.04
        - CMD date

When we do something like ``harpoon run second`` it will create images for both
of them, and then create a container for the ``first`` image, wait for the
condition to be met (in this case waiting for ``/tmp/wait`` to exist in the
container) and then, when that condition is met, will start the ``second``
container and link it with the first.

There are several different conditions you may specify:

greps
    A dictionary of <file to grep>: <string to grep for>

command
    A list of commands that must be met

port_open
    A list of ports that must be waiting for traffic (tested with ``nc -z 127.0.0.1 <port>``)

file_value
    A dictionary of <file>: <expected content>

curl_result
    A dictionary of <url>: <expected result>

file_exists
    A list of files to look for

You also have these two options:

timeout
  Fail waiting for the container after this amount of time

wait_between_attempts
  Wait atleast this long between attempting to resolve all the conditions

You may also specify wait_conditions for dependencies on the container that uses
those dependencies:

.. code-block:: yaml

  ---

  images:
    first:
      commands:
        - FROM ubuntu:14.04
        - CMD sleep 4 && touch /tmp/wait

    second:

      dependency_options:
        first:
          wait_condition:
            file_exists:
              - /tmp/wait

      links:
        - "{image.first}"

      commands:
        - FROM ubuntu:14.04
        - CMD date

Wait conditions specified this way will overwrite any wait_conditions set by the
dependency itself.

Port bound detection
--------------------

One of the more annoying errors that can happen is if a container wants to bind
to a port that already exists, harpoon would just complain saying the container
exited with a nonzero exit code before it even started.

With this new feature since version 0.5.8.2 Harpoon will try and work out if
the required ports are already bound and complain if they are:

.. code-block:: yaml

  ---

  images:
    my_image:
      context: false
      commands:
        - FROM ubuntu:14.04
        - CMD python3 -m http.server 9000

      tasks:
        runner:
          description: Run our python server in the docker container
          options:
            ports:
              - "9000:9000"

.. code-block:: text

  $ python3 -m http.server 9000 &
  $ harpoon runner
  11:06:37 INFO    harpoon.executor Connected to docker daemon    driver=aufs     kernel=4.1.17-boot2docker
  11:06:37 INFO    option_merge.collector Adding configuration from /Users/stephen.moore/.harpoonrc.yml
  11:06:37 INFO    option_merge.collector Adding configuration from /Users/stephen.moore/deleteme/harpoon.yml
  11:06:37 INFO    harpoon.collector Converting harpoon
  11:06:37 INFO    harpoon.collector Converting images.my_image
  11:06:37 INFO    harpoon.ship.builder Making image for 'my_image' (my_image) - FROM ubuntu:14.04
  11:06:37 INFO    harpoon.ship.builders.mixin Building 'my_image' in '/Users/stephen.moore/deleteme' with 10.2 kB of context
  Step 1 : FROM ubuntu:14.04
  ---> 06ab2de020f4
  Step 2 : CMD python3 -m http.server 9000
  ---> Running in 32200c32359a
  ---> 15052fde2407
  Removing intermediate container 32200c32359a
  Successfully built 15052fde2407
  11:06:38 INFO    harpoon.ship.runner Creating container from my_image   image=my_image  container_name=my_image-4826b066-1582-11e6-a2d8-20c9d088bcc7    tty=True
  11:06:38 INFO    harpoon.ship.runner    Using ports     ports=[9000]
  11:06:38 INFO    harpoon.ship.runner    Port bindings: [9000]
  11:06:38 INFO    harpoon.executor Connected to docker daemon    driver=aufs     kernel=4.1.17-boot2docker
  11:06:38 INFO    harpoon.ship.runner Removing container my_image-4826b066-1582-11e6-a2d8-20c9d088bcc7:ec5867550aeff206fd4d64258053e123fe092f96148725634e66f977a6513609

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  Something went wrong! -- AlreadyBoundPorts
          "Ports are already bound by something else"     ports=[9000]

Authentication
--------------

Harpoon supports authentication for registries via plain credentials, Kms
encrypted credentials or via a "slip" in an S3 bucket.

It also supports loging into Google Container registry. Logging into gcr happens
automatically and without user configuration if the image_index has gcr.io in
it. (Note however, that this requires a `docker` binary to be installed on your
PATH.

.. code-block:: yaml

  authentication:
    registry.my-amazing-company.com.au
      reading:
        use: plain
        username: bob
        password: super_s3cr3t
      writing:
        use: kms
        role: arn:aws:iam::1234544232:role/kms-reader
        region: ap-southeast-2
        username: bob
        password: CiB1pqppldpSEDooCLKBYvCRHy/qWPs9+yJ0eUJ0MKRHsxKLAQEBAgB4daaqaZXaUhA6KAiygWLwkR8v6lj7PfsidHlCdDCkR7MAAABiMGAGCSqGSIb3DQEHBqBTMFECAQAwTAYJKoZIhvcNAQcBMB4GCWCGSAFlAwQBLjARBAzo+RPkrpz3+4riJkQCARCAH7NXjqqu0OSmYtiNXK7SrUw3mzWa8NYy5KfC4RKGFTQ=

    registry.my-other-amazing-company.com.au
      reading:
        use: s3_slip
        role: arn:aws:iam::124879330703/role/s3_reader
        location: s3://my-amazing-slips/the-slip.txt

Plain authentication is what it says, just plain text and use as is. Kms encrypted
means that the password is a base64 encoded encrypted string that is decrypted
with kms after assuming the specified role.

S3 Slips are a special construct where there is a file in s3 containing a string
of "username:password" and harpoon will assume the specified role and use that to
get the slip and extract the username and password from it.

S3 slips are nice in that they can be rotated and the client doesn't need to know
that it's been rotated (so long as it gets the new creds each time it interacts
with the registry)

Squashing containers
--------------------

Currently if you want to squash your containers, you must rely on the third party
`docker squash <https://github.com/jwilder/docker-squash>`_ tool.

Harpoon loosely integrates with this tool using the ``squash_after`` and
``squash_before_push`` options.

The ``squash_after`` option means that docker-squash will be used every time the
image is built, whereas ``squash_before_push`` is used only if the image is
about to be pushed by harpoon.

Both options can be either a boolean saying ``true`` or ``false``; or can be a
list of extra DockerFile commands to use before squashing the image.

If extra DockerFile commands are specified, an intermediate image is created with
these extra commands and it's the intermediate image that will be squashed.

For example:

.. code-block:: yaml

  images:
      with_node:
        image_index: <wherever your docker index is>
        commands:
          - FROM ubuntu:14.04
          - RUN apt-get update && apt-get install software-properties-common -y
          - RUN add-apt-repository ppa:chris-lea/node.js
          - RUN apt-get update && apt-get install -y nodejs
          - RUN mkdir /project

        squash_before_push:
          - RUN sudo apt-get clean

        tasks:
          node_version:
            options:
              command: node --version

With this configuration we can run our ``node_version`` task without having to
wait for docker-squash to do it's thing and when we're ready, ``harpoon push with_node``
will build and squash and push the image.

