from setuptools import setup, find_packages
from harpoon import VERSION

setup(
      name = "docker-harpoon"
    , version = VERSION
    , packages = ['harpoon'] + ['harpoon.%s' % pkg for pkg in find_packages('harpoon')]
    , include_package_data = True

    , install_requires =
      [ "delfick_app==0.9.5"
      , "option_merge==1.6"
      , "input_algorithms==0.6.0"
      , "option_merge_addons==0.2"

      , "docker==2.4.2"

      , "six"
      , "glob2"
      , "humanize"

      , "boto3==1.4.4"
      , "pyYaml==3.12"
      ]

    , extras_require =
      { "tests":
        [ "noseOfYeti>=1.7"
        , "nose"
        , "mock==1.0.1"
        , "nose-pattern-exclude"
        , "nose-focus==0.1.2"
        , "tox"
        ]
      , "git":
        [ "gitmit==0.3"
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
    , license = "MIT"
    , keywords = "docker"
    )

