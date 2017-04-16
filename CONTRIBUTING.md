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

And then `harpoon` is in your PATH

# Intro to Harpoon

## Harpoon consists of 4 things:
* Harpoon (app)
* delfick_error (supporting library)
* option_merge (supporting library)
* input_algorithms (supporting library)

## [Delfick Error](https://github.com/delfick/delfick_error):
Custom Exception class (orderable, hashable, pretty_printed, supports testing)

## [Option Merge](https://github.com/delfick/option_merge):
* Deep merge of Python dictionaries
* Enables deep referencing
* Supports conversion on reference (memoises)

## [Input Algorithms](https://github.com/delfick/input_algorithms):
Specify a .yaml and verifies, converts and normalises it to python objects

## Harpoon:
* Docker client that reads a .yaml spec
* Takes a .yaml file,
* parses arguments, logging,
* harpoon args, cli args and task args
* Create the harpoon class then run

Harpoon Class:
* Collects configuration, sets up logging
* Configuration comes from ~/.harpoon.yml
* then #{local folder}/harpoon.yml

Additional .yml files can be specified with

```
images:
  __images_from__: <folder to .yml>
```

## Sequence of events
File.read(~/harpoon.yml, <local>.yml, <image_from>*.yml) -> MergedOptions
cli args tacked on
config_root tacked on (where harpoon.yml is specified)

### Go through images dir
* for each image
  * find a task
  * interpret the task with the given config
  * convert each task to a TaskObject
* set a chosen task (harpoon.chosen_task)
* run the task
* chosen_task = --task or harpoon_chosen_task
* Positional arg parsing

CliParser 'pattern'
