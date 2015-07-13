from setuptools import setup, find_packages
from harpoon import VERSION

setup(
      name = "docker-harpoon"
    , version = VERSION
    , packages = ['harpoon'] + ['harpoon.%s' % pkg for pkg in find_packages('harpoon')]
    , include_package_data = True

    , install_requires =
      [ "delfick_app==0.6.7"
      , "option_merge==0.9.8.1"
      , "input_algorithms==0.4.4.3"

      , "docker-py==1.2.2"
      #, "dockerpty==0.3.2"

      , "six"
      , "glob2"
      , "dulwich"
      , "humanize"

      , "pyYaml==3.10"
      ]

    , extras_require =
      { "tests":
        [ "noseOfYeti>=1.5.0"
        , "nose"
        , "mock==1.0.1"
        , "nose-pattern-exclude"
        , "nose-focus==0.1.2"
        , "tox"
        ]
      }

    , entry_points =
      { 'console_scripts' :
        [ 'harpoon = harpoon.executor:main'
        ]
      }

    # metadata for upload to PyPI
    , url = "https://github.com/realestate-com-au/harpoon"
    , author = "Stephen Moore"
    , author_email = "stephen.moore@rea-group.com"
    , description = "Opinionated wrapper around docker"
    , license = "MIT"
    , keywords = "docker"
    )

