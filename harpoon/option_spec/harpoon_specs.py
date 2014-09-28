from input_algorithms.spec_base import (
      create_spec, defaulted, string_choice_spec
    , dictionary_spec, string_spec, valid_string_spec, dictof
    )

from harpoon.helpers import memoized_property
from input_algorithms import validators
from harpoon.option_spec import objs

class HarpoonSpec(object):
    """Knows about harpoon specific configuration"""

    @memoized_property
    def image_name_spec(self):
        """
        Image names are constrained by what docker wants

        And by the fact that option_merge means we can't have keys with dots in them.
        Otherwise if we have something like "ubuntu14.04" as an image, then when we do
        {images.ubuntu14.04.image_name} it'll look for config["images"]["ubuntu14"]["04"]["image_name"]
        instead of config["images"]["ubuntu14.04"]["image_name"] which is unlikely to be the
        desired result.
        """
        return valid_string_spec(
              validators.no_whitespace()
            , validators.regexed("^[a-zA-Z][a-zA-Z0-9-_\.]*$")
            )

    @memoized_property
    def task_name_spec(self):
        """We restrict this for the same reasons as the image_name_spec"""
        return valid_string_spec(
              validators.no_whitespace()
            , validators.regexed("^[a-zA-Z][a-zA-Z0-9-_\.]*$")
            )

    def tasks_spec(self, available_actions, default_action="run"):
        """Tasks for a particular image"""
        return dictof(
              self.task_name_spec
            , create_spec(objs.Task, validators.deprecated_key("spec", "Use ``action`` and ``options`` instead (note that ``action`` defaults to run)")
                , action = defaulted(string_choice_spec(available_actions, "No such task"), default_action)
                , options = dictionary_spec()
                , overrides = dictionary_spec()
                , description = string_spec()
                )
            )

