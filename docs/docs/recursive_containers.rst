.. _recursive_containers:

Recursive Containers
====================

One of the things you lose out on when you start using docker containers is the
caching systems that come with our package management software.

This means that when we get our dependencies in a docker file, it only takes a
change to one of the dependencies to trigger getting all the dependencies.

It would be great if we could somehow persist the cache directories used by our
tools between builds so that we can utilise this functionality.

Recursive containers is a hack using docker `data volumes <https://docs.docker.com/userguide/dockervolumes/>`_
to achieve just that.

Let's say we have the following configuration:

.. code-block:: yaml

    ---

    context: false

    images:
      with_node:
        commands:
          - FROM ubuntu:14.04
          - RUN apt-get update && apt-get install -y software-properties-common
          - RUN add-apt-repository ppa:chris-lea/node.js
          - RUN apt-get update && apt-get install -y nodejs
          - RUN mkdir /project

      dependencies:
        # Here we define our recursive block
        # It takes the final action that generates our cache
        # And a list of folders that get persisted between builds
        recursive:
          action: cd /project && npm install
          persist: /project/node_modules

        commands:
          - [FROM, "{images.with_node}"]
          - - ADD
            - dest: /project/package.json
              content: |
                { "name": "writer"
                , "version": "0.0.0"
                , "dependencies":
                  { "ascii-art": "*"
                  }
                }

        tasks:
          write:
            description: Write some ascii art
            options:
              bash: cd /project && node -e "art = require(\"ascii-art\"); art.font(\"{$@}\", \"Doom\", function(rendered) {{ console.log(rendered) }})"

Now we can run a command like ``harpoon write -- blah`` and it will print us
``blah`` in pretty block letters.

We can now also change things in the package.json and any dependency already
downloaded into node_modules does not need to be redownloaded because the folder
is effectively saved between builds.

Example with sbt
----------------

Let's do another example, this time with a Scala Play! application.

We can do something like:

.. code-block:: yaml

    ---

    context:
      parent_dir: "{config_root}"
      use_gitignore: true
      use_git_timestamps: true

    images:
      prepared:
        context: false

        commands:
          - FROM ubuntu:14.04

          - RUN sudo apt-get -y install software-properties-common unzip wget

          ## Install java 7
          - RUN sudo add-apt-repository -y ppa:webupd8team/java
          - RUN sudo apt-get update
          - RUN echo debconf shared/accepted-oracle-license-v1-1 select true | debconf-set-selections
          - RUN echo debconf shared/accepted-oracle-license-v1-1 seen true | debconf-set-selections
          - RUN sudo apt-get -y install oracle-java7-installer

          ## Download sbt
          - RUN wget -O /tmp/sbt.tar.gz https://dl.bintray.com/sbt/native-packages/sbt/0.13.6/sbt-0.13.6.tgz

          ## Install the sbt
          - RUN tar xf /tmp/sbt.tar.gz -C /opt
          - ENV PATH /opt/sbt/bin:$PATH

          ## Make sbt download itself
          - RUN sbt tasks

      resolved:
        recursive:
          action: cd /project && sbt update
          persist:
            - /project/target/
            - /project/project/target/
            - /project/project/project/
            - /root/.sbt/
            - /root/.ivy2/
        commands:
          - [FROM, "{images.prepared}"]
          - ADD project/build.properties /project/project/build.properties
          - ADD project/plugins.sbt /project/project/plugins.sbt

      compiled:
        recursive:
          action: cd /project && sbt compile && sbt test:compile
          persist:
            - /project/target/
            - /project/project/target/
            - /project/project/project/
            - /root/.sbt/
            - /root/.ivy2/

        commands:
          - [FROM, "{images.resolved}"]
          - ADD . /project

      installed:
        commands:
          - [FROM, "{images.compiled}"]

        tasks:
          unit_tests:
            options:
              bash: "cd /project && sbt test"
            description: "Run the unit tests"

And now we can run ``harpoon unit_tests`` and will only have to resolve any new
dependencies and only have to compile new/changed files.

Alternative use
---------------

One problem you may have is you might want to include multiple recursive
containers or for some reason not chain the containers together like we've been
doing.

In that case, we can copy the persisting folders in at container time using the
"{images.<container>.recursive.precmd}" variable instead.

For example, our sbt application at the top can be redone as below (the only
thing that changes is the ``installed`` image at the bottom):

.. code-block:: yaml

    ---

    context:
      parent_dir: "{config_root}"
      use_gitignore: true
      use_git_timestamps: true

    images:
      prepared:
        context: false

        commands:
          - FROM ubuntu:14.04

          - RUN sudo apt-get -y install software-properties-common unzip wget

          ## Install java 7
          - RUN sudo add-apt-repository -y ppa:webupd8team/java
          - RUN sudo apt-get update
          - RUN echo debconf shared/accepted-oracle-license-v1-1 select true | debconf-set-selections
          - RUN echo debconf shared/accepted-oracle-license-v1-1 seen true | debconf-set-selections
          - RUN sudo apt-get -y install oracle-java7-installer

          ## Download sbt
          - RUN wget -O /tmp/sbt.tar.gz https://dl.bintray.com/sbt/native-packages/sbt/0.13.6/sbt-0.13.6.tgz

          ## Install the sbt
          - RUN tar xf /tmp/sbt.tar.gz -C /opt
          - ENV PATH /opt/sbt/bin:$PATH

          ## Make sbt download itself
          - RUN sbt tasks

      resolved:
        recursive:
          action: cd /project && sbt update
          persist:
            - /project/target/
            - /project/project/target/
            - /project/project/project/
            - /root/.sbt/
            - /root/.ivy2/
        commands:
          - [FROM, "{images.prepared}"]
          - ADD project/build.properties /project/project/build.properties
          - ADD project/plugins.sbt /project/project/plugins.sbt

      compiled:
        recursive:
          action: cd /project && sbt compile && sbt test:compile
          persist:
            - /project/target/
            - /project/project/target/
            - /project/project/project/
            - /root/.sbt/
            - /root/.ivy2/

        commands:
          - [FROM, "{images.resolved}"]
          - ADD . /project

      installed:
        commands:
          - [FROM, "{images.prepared}"]

        persist:
          # Share the volumes from our recursive images with this image
          # Note that the order here is important because compiled has the
          # same shared folder as resolved
          share_with:
            - "{images.compiled}"
            - "{images.resolved}"

        vars:
          # We define a variable here that we use in our unit_tests task
          # This takes the precmd and rmcmd from our recursive images and strings them together
          # These commands will wait for the shared folders to be ready before untarring their goods into place
          precmd: "{images.compiled.recursive.precmd} && {images.resolved.recursive.precmd} && {images.resolved.recursive.rmcmd} && {images.compiled.recursive.rmcmd}"

        tasks:
          unit_tests:
            options:
              bash: "{images.installed.vars.precmd} && cd /project && sbt test"
            description: "Run the unit tests"


Now, unfortunately, we can't share volumes at build time so what we do here is
construct an image with the cache folder inside: run it as a container with a
shared volume and copy the cache into that shared volume.

Then in the container that needs the cache folder we copy the cache from the
shared volume into the container and proceed to use it.

How does it work?
-----------------

Harpoon builds the recursive image using several different dockerfiles based off
the commands in the recursive image and the action specified by the recursive
image.

The first time it is built, it creates a docker file that is the commands plus
the action plus a ``CMD`` that copies the folders specified by ``persist`` into
a docker volume.

If the recursive image already exists then harpoon will figure out if the docker
cache is broken by any of the layers in the specified commands.

If the cache is not broken, then it doesn't do anything, we already have a
recursive image. (Note that this does mean changing the action may not trigger
a new build).

If the cache is broken, then it creates two containers:

changer
    This is a dockerfile that does a "FROM <recursive image>" followed by
    all the commands and the action and a ``CMD`` that copies the ``persist``
    folders into a docker volume.

builder
    This is a dockerfile with the normal commands and a ``CMD`` that copies
    the ``persist`` folders from the shared volume into their place in the
    container.

    This container is run, sharing volumes with the changer and when it's finished,
    it is committed and tagged as the new recursive image.

    This step is necessary to make sure that we don't just keep growing the
    number of layers used by the recursive image.

If the recursive image isn't referenced in any ``volumes.share_with`` for another
container, then harpoon doesn't need to build anymore images or containers at
this point.

If there is a reference, however, then it needs to create a ``provider`` container.

This is a container that inherits from the recursive image and just has a ``CMD``
that copies the ``persist`` folders into a docker volume.

When you share volumes with a recursive image, you're actually sharing volumes
with a ``provider``.

