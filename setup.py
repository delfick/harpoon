from setuptools import setup, find_packages
from harpoon import VERSION

# fmt: off

setup(
      name = "docker-harpoon"
    , version = VERSION
    , packages = find_packages(include="harpoon.*", exclude=["tests*"])
    , include_package_data = True

    , python_requires = ">= 3.6"

    , install_requires =
      [ "delfick_project==0.7.0"

      , "docker==3.5.0"

      , "humanize"

      , "ruamel.yaml==0.16.5"
      , "rainbow_logging_handler==2.2.2"
      ]

    , extras_require =
      { "tests":
        [ "noseOfYeti==1.9.1"
        , "psutil==5.6.3"
        , "pytest"
        , "tox"
        ]
      }

    , entry_points =
      { 'console_scripts' :
        [ 'harpoon = harpoon.executor:main'
        ]
      }

    # metadata for upload to PyPI
    , url = "https://github.com/delfick/harpoon"
    , author = "Stephen Moore"
    , author_email = "delfick755@gmail.com"
    , description = "Opinionated wrapper around docker"
    , long_description = open("README.rst").read()
    , license = "MIT"
    , keywords = "docker"
    )

# fmt: on
