# Contributing
Local dev is the same as any python project

## Install pip
Instructions at http://pip.readthedocs.org/en/latest/installing.html

## Install virtualenv
Instructions at http://virtualenv.readthedocs.org/en/latest/virtualenv.html#installation

## Make a virtualenv (from the `harpoon` directory).
``` bash
virtualenv .
pip install -e .
```

And then harpoon is in your PATH

Instead of using harpoon.sh you just use the harpoon binary in your path
(harpoon.sh activates it's own virtualenv)

And you can create a debugger by doing `"from pdb import set_trace; set_trace()"` anywhere
