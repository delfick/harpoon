.. _bh_s1_introduce_dockerpy:

S1: Introduce Docker-py
=======================

Ok, let's do some Docker!

Docker is a thing that exists, it does resource isolation such that it appears
an entire operating system is running in an isolated "container".

There are three concepts in particular that need to be understood when it comes
to Docker:

Docker daemon
    Docker uses a Server-client architecture where the server runs somewhere as
    a Daemon and performs all the hard work.

    A client is a piece of software that talks to the daemon over http, telling
    it what to do.

    Harpoon is a docker *client*. The only thing it does is get the daemon to do
    it's dirty work for it.

Docker images
    An image is a collection of folders that are merged together at runtime to
    create one filesystem.

    Where that filesystem contains everything necessary to run one or more
    processes.

    Typically this includes an entire operating system.

Docker container
    A process running against a docker image.

    You can think of a container as an *instance* of an image.

These concepts will start to make more sense as you start to implement Harpoon.

requirements.txt
----------------

First, we must get the ``docker-py`` and ``dockerpty`` libraries.

docker-py
    A Python library that exposes a object orientated interface to the HTTP API
    exposed by the docker daemon.

    i.e. you can say docker.push("my_amazing_image") instead of
    requests.post("http://docker_daemon/images/my_amazing_image/push")

dockerpty
    A python library that does the hard work of creating a tty.

    This library means we don't have to do annoying things to display the output
    from running a container.

Harpoon uses a ``setup.py`` file to define it's requirements, but that's a bit
overkill for our example at the moment, so we'll just use a ``requirements.txt``

.. code-block:: text

    docker-py==1.2.2
    dockerpty==0.3.4
    requests[security]

and then, after making sure your virtualenv is activated, run::

    $ pip install -r requirements.txt

This will download the requirements in your ``requirements.txt`` into your
virtualenv, so when we start up Python, we may import those in.

Now, hello world for docker-py:

.. code-block:: python

    import docker

    def main():
        client = docker.Client()
        print(client.info())

``./harpoon.py``

If that didn't work, then perhaps you need to actually start Docker :)

Have a look at https://docs.docker.com/machine/

Unfortunately if it's **still not working**, it's probably because you're connecting
over tls and we need to pass in some parameters to ``Client()``. Fortunately
``docker-py`` has a helper for just this scenario.

So let's do this:

.. code-block:: python

    import docker
    import ssl
    import os

    def make_client():
        """Make a docker client"""
        return docker.Client(**docker.utils.kwargs_from_env(assert_hostname=False))

    def main():
        client = make_client()
        print(client.info())

Once you have that working, let's make it pretty.

Because we can!

.. code-block:: python

    import json

    def main():
        client = make_client()
        print(json.dumps(client.info(), indent=4))

``./harpoon.py``

Making an image
---------------

Well, that was fun. Now let's do something a bit more interesting:

.. code-block:: python

    import tempfile

    def main():
        client = make_client()
        dockerfile_commands = [
          "FROM gliderlabs/alpine:3.1"
        , "RUN apk-install figlet --update-cache --repository http://dl-3.alpinelinux.org/alpine/edge/main/"
        , "CMD figlet lolz"
        ]

        dockerfile = tempfile.NamedTemporaryFile(delete=True)
        dockerfile.write("\n".join(dockerfile_commands))
        dockerfile.flush()
        dockerfile.seek(0)

        for line in client.build(fileobj=dockerfile, rm=True, tag="local/figlet", pull=False):
            print(line)

``./harpoon.py``

Congratulations! You made a docker image!

Now let's run it::

    $ docker run -it local/figlet

Wooh! We turned it into a container that ran the command "figlet lolz" and
printed out a super cool ASCII art of the word 'lolz'

Making the container with Python
--------------------------------

Now let's use dockerpty to start our container:

.. code-block:: python

    import dockerpty

    def main():

        [..]

        for line in client.build(fileobj=dockerfile, rm=True, tag="local/figlet", pull=False):
            print(line)

        container = client.create_container(image='local/figlet')
        dockerpty.start(client, container)

``./harpoon.py``

Now if you've seen some error complaining about ``http: Hijack is incompatible
with use of CloseNotifier`` then you've come across a bug in docker that means
we need to create a new client when we run a container, so let's do that.

.. code-block:: python

    import dockerpty

    def main():
        [..]

        dockerpty.start(make_client(), container)

Cleaning up
-----------

Lets do::

    $ docker ps -a

You'll probably see a lot of ``exited`` containers with a command that looks like
``"/bin/sh -c 'figlet``.

What's happening is we are creating containers, running them and then just
leaving them there and nothing is clearing them away!

So, for these existing containers::

    $ docker ps -aq | xargs docker rm

Will clean them up, and now we will add code that does the cleanup as part of
the program:

.. code-block:: python

    [..]

    dockerpty.start(make_client(), container)
    client.remove_container(container)

``./harpoon.py``

Now when we do ``docker ps -a`` we shouldn't see any more containers.

