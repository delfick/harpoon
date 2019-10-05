Documentation
=============

To build the documentation run::

   $ ./build_docs

If you want to build from fresh then say::

   $ ./build_docs fresh

Once your documentation is built do something like::

   $ python3 -m http.server 9088

And go to http://localhost:9088/_build/html/index.html
