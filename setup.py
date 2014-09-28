from setuptools import setup, find_packages
from harpoon import VERSION

setup(
      name = "docker-harpoon"
    , version = VERSION
    , packages = ['harpoon'] + ['harpoon.%s' % pkg for pkg in find_packages('harpoon')]
    , include_package_data = True

    , install_requires =
      [ "delfick_error==1.6"
      , "option_merge==0.8.1"
      , "input_algorithms==0.3.5"

      , "docker-py==0.4.0"
      , "dockerpty==0.2.3"

      , "humanize"
      , "glob2"
      , "namedlist"
      , "pyYaml==3.10"
      , "rainbow_logging_handler==2.2.2"
      ]

    , extras_require =
      { "tests":
        [ "noseOfYeti>=1.5.0"
        , "nose"
        , "mock"
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

