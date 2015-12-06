.. _persistence:

Persistence
===========

One of the things you lose out on when you start using docker containers is the
caching systems that come with our package management software.

This means that when we get our dependencies in a docker file, it only takes a
change to one of the dependencies to trigger getting all the dependencies.

It would be great if we could somehow persist the cache directories used by our
tools between builds so that we can utilise this functionality.

The persistence feature in harpoon allows us to do just that, but using docker
volumes.

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
        # Here we define our persistence block
        # It takes the final action that generates our cache
        # And a list of folders that get persisted between builds
        persistence:
          action: cd /project && npm install
          folders: /project/node_modules

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
        persistence:
          action: cd /project && sbt update
          folders:
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
        persistence:
          action: cd /project && sbt compile && sbt test:compile
          folders:
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

How does it work?
-----------------

Harpoon uses the fact that it generates the docker file to create several docker
files on your behalf and use that to transfer the folders from one image to
another using a shared volume.

The workflow is as follows:

No existing image
    If the image doesn't already exist, then we generate a dockerfile that is
    the commands from that image plus the action.

    After this we are done!

Existing image
    If we already have an image, then we want to steal the persisting folders
    before running the action again.

    So we create a dockerfile that moves those folders into a central location,
    before turning it into a VOLUME. So a docker file that looks like:

    .. code-block::

        FROM <existing image>
        RUN <move folders to /shared>
        VOLUME /shared
        CMD while true; do sleep 5; done

    We then make the "second" dockerfile which looks like:

    .. code-block::

        <original docker commands>
        CMD <move folders from /shared into place> && <action>

    We run these two images as containers and share the /shared volume. When
    the second dockerfile is finished we then commit it into an image.

    Finally, we construct a "final" dockerfile:

    .. code-block::
        
        FROM <image from committing the second dockerfile>
        CMD <specified cmd in the options or /bin/bash>

    And this is tagged as our image!

    Once that is all done, we clean up our loose ends.

As an optimisation, harpoon will also do a test to see if any of the commands,
folders or action has changed since the last time the image was made and won't
go through the process if they haven't changed.

