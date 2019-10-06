.. _container_manager:

Container Manager
=================

Harpoon provides a way of requesting containers via a web server, called the
container manager.

For example, you could have a config like:

.. code-block:: yaml

   ---

   images:
      server:
         context: false

         commands:
            - FROM python:3
            - - ADD
              - dest: /example_file
                content: "hello there"
            - CMD python -m http.server 4545

And then, using this config file as your configuration, run::

   $ harpoon container_manager

By default, this will start the server on port 4545, see :ref:`below <container_manager_options>`
for more information on the options to the container manager.

You can then request an image by doing something like::

   $ curl -XPOST http://localhost:4545/start_container \
      -HContent-Type:application/json \
      -d '{"image": "server", "ports": [[0, 4545]]}' 

Which will return something like:

.. code-block:: json

   {
      "ports": {"4545": 32772},
      "just_created": true,
      "container_id": "73843d875d62cded348e1bba08ef8ba567d6f8a20feb078d8beb4170a9f85965"
   }

This says that port 4545 in the container is mapped to port 32772 on your host.

And with that port, we can now say::

   $ curl http://localhost:32772/example_file
   hello there

If you do the start_container POST again, then it will reuse this same container
and return the same response, but say "just_created: false".

You can then either explicitly stop this container by saying::

   $ curl -XPOST http://localhost:4545/stop_container \
      -HContent-Type:application/json \
      -d '{"image": "server"}' 

Which will return an empty 204 response.

Or you can leave it and it'll be cleaned up when you shut down the container
manager.

You can shutdown the container manager by either ctrl-c'ing the process, or
sending it a SIGTERM or by making a GET request to /shutdown::

   $ curl http://localhost:4545/shutdown

When the container manager stops, any running containers will be stopped and
removed from docker.

The last endpoint is /version which will return something like::

   $ curl http://localhost:4545/version
   harpoon 0.16.0

.. _container_manager_options:

Container Manager Options
-------------------------

When you start the container manager, it takes in one positional argument that
specifies how it starts and what port it serves on.

When you start the container manager without options, it's the same as saying::

   $ harpoon container_manager :4545

Which says start the container manager in the foreground and run it on port 4545.

You can also tell harpoon to start in the background by giving it a path to a
file::

   $ harpoon container_manager /path/to/file:4545

This will fork the process and write to ``/path/to/file`` the port the manager
started on and the pid of the child::

   <port>
   <pid>

For example, if the pid was 92564, then in this case the file would look like::

   4545
   92564

When you specify a file, but not a port then it will choose a free port on your
system::

   $ harpoon container_manager /path/to/file

Starting the container manager is useful if you want to start it and then run
something else that uses it. For example, you could say something like:

.. code-block:: bash

    #!/bin/bash
    
    set -e
    
    info=$(mktemp)
    cleanup() { rm $info; }
    trap cleanup EXIT
    
    # container_manager will exit with an error status if we couldn't start
    # The container manager. But because we gave it just a file, it'll run the
    # web server in the background and the script will continue
    harpoon container_manager $info --non-interactive
    
    PORT=$(head -n1 $info)
    export HARPOON_CONTAINER_MANAGER="http://localhost:$PORT"
    
    cleanup() {
        if ! rm $info; then
            echo "Failed to remove temporary file at $info"
        fi
        curl "$HARPOON_CONTAINER_MANAGER/shutdown"
    }
    trap cleanup EXIT
    
    # Run tests
    bazel test
