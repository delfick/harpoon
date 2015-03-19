"""
Here we define the yaml specification for Harpoon options, task options and image
options.

The specifications are responsible for sanitation, validation and normalisation.
"""

from input_algorithms.spec_base import (
      create_spec, defaulted, string_choice_spec
    , dictionary_spec, string_spec, valid_string_spec
    , listof, optional_spec, or_spec, any_spec
    , directory_spec, filename_spec, file_spec
    , boolean, required, formatted, overridden
    , integer_spec, dictof, dict_from_bool_spec
    , container_spec
    )

from harpoon.option_spec.command_specs import command_spec
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.option_spec.command_objs import Commands
from harpoon.helpers import memoized_property
from harpoon.option_spec import task_objs

from input_algorithms.dictobj import dictobj
from input_algorithms import validators

import time
import six

class Harpoon(dictobj):
    fields = [
          "config", "chosen_image", "chosen_task", "flat", "silent_build"
        , "extra", "no_intervention", "ignore_missing", "keep_replaced"
        , "interactive", "do_push", "only_pushable", "docker_context", "no_cleanup"
        ]

class other_options(dictobj):
    fields = ["run", "create", "build"]

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
        """Just needs to be ascii"""
        return valid_string_spec(
              validators.no_whitespace()
            , validators.regexed("^[a-zA-Z][a-zA-Z0-9-_\.]*$")
            )

    @memoized_property
    def container_name_spec(self):
        """Just needs to be ascii"""
        return valid_string_spec(
              validators.no_whitespace()
            , validators.regexed("^[a-zA-Z][a-zA-Z0-9-_\.]*$")
            )

    def tasks_spec(self, available_actions, default_action="run"):
        """Tasks for a particular image"""
        return dictof(
              self.task_name_spec
            , create_spec(task_objs.Task, validators.deprecated_key("spec", "Use ``action`` and ``options`` instead (note that ``action`` defaults to run)")
                , action = defaulted(string_choice_spec(available_actions, "No such task"), default_action)
                , options = dictionary_spec()
                , overrides = dictionary_spec()
                , description = string_spec()
                )
            )

    @memoized_property
    def image_spec(self):
        """Spec for each image"""
        from harpoon.option_spec import image_specs as specs
        from harpoon.option_spec import image_objs
        return create_spec(image_objs.Image
            # Change the context options
            , validators.deprecated_key("exclude_context", "Use ``context.exclude``")
            , validators.deprecated_key("use_git_timestamps", "Use ``context.use_git_timestamps``")
            , validators.deprecated_key("respect_gitignore", "Use ``context.use_gitignore``")
            , validators.deprecated_key("parent_dir", "Use ``context.parent_dir``")

            # Changed how volumes_from works
            , validators.deprecated_key("volumes_from", "Use ``volumes.share_with``")

            # Deprecated link
            , validators.deprecated_key("link", "Use ``links``")

            # Harpoon options
            , harpoon = any_spec()

            # default the name to the key of the image
            , name = formatted(defaulted(string_spec(), "{_key_name_1}"), formatter=MergedOptionStringFormatter)
            , key_name = formatted(overridden("{_key_name_1}"), formatter=MergedOptionStringFormatter)
            , image_name = optional_spec(string_spec())
            , image_index = defaulted(string_spec(), "")
            , container_name = optional_spec(string_spec())
            , image_name_prefix = defaulted(string_spec(), "")

            , user = defaulted(string_spec(), None)
            , mtime = defaulted(any_spec(), time.time())
            , configuration = any_spec()

            # The spec itself
            , bash = optional_spec(formatted(string_spec(), formatter=MergedOptionStringFormatter))
            , command = optional_spec(formatted(string_spec(), formatter=MergedOptionStringFormatter))
            , commands = required(container_spec(Commands, listof(command_spec())))
            , links = listof(specs.link_spec(), expect=image_objs.Link)

            , context = dict_from_bool_spec(lambda meta, val: {"enabled": val}
                , create_spec(image_objs.Context
                    , include = listof(string_spec())
                    , exclude = listof(string_spec())
                    , enabled = defaulted(boolean(), True)

                    , parent_dir = directory_spec(formatted(defaulted(string_spec(), "{config_root}"), formatter=MergedOptionStringFormatter))
                    , use_gitignore = defaulted(boolean(), False)
                    , use_git_timestamps = defaulted(or_spec(boolean(), listof(string_spec())), False)
                    )
                )

            , lxc_conf = defaulted(filename_spec(), None)

            , volumes = create_spec(image_objs.Volumes
                , mount = listof(specs.mount_spec(), expect=image_objs.Mount)
                , share_with = listof(formatted(string_spec(), MergedOptionStringFormatter, expected_type=image_objs.Image))
                )

            , dependency_options = dictof(self.image_name_spec
                , create_spec(image_objs.DependencyOptions
                  , attached = defaulted(boolean(), False)
                  )
                )

            , env = listof(specs.env_spec(), expect=image_objs.Environment)
            , ports = listof(specs.port_spec(), expect=image_objs.Port)

            , other_options = create_spec(other_options
                , run = dictionary_spec()
                , build = dictionary_spec()
                , create = dictionary_spec()
                )

            , network = create_spec(image_objs.Network
                , dns = defaulted(listof(string_spec()), None)
                , mode = defaulted(string_spec(), None)
                , hostname = defaulted(string_spec(), None)
                , domainname = defaulted(string_spec(), None)
                , disabled = defaulted(boolean(), False)
                , dns_search = defaulted(listof(string_spec()), None)
                , extra_hosts = optional_spec(listof(string_spec(), None))
                , publish_all_ports = defaulted(boolean(), False)
                )

            , cpu = create_spec(image_objs.Cpu
                , cap_add = defaulted(boolean(), None)
                , cpuset = defaulted(listof(string_spec()), None)
                , cap_drop = defaulted(boolean(), None)
                , mem_limit = defaulted(integer_spec(), 0)
                , cpu_shares = defaulted(integer_spec(), None)
                , memswap_limit = defaulted(integer_spec(), 0)
                )

            , devices = defaulted(listof(string_spec()), None)
            , privileged = defaulted(boolean(), False)
            , restart_policy = defaulted(string_spec(), None)
            )

    @memoized_property
    def harpoon_spec(self):
        """Spec for harpoon options"""
        formatted_string = formatted(string_spec(), MergedOptionStringFormatter, expected_type=six.string_types)
        formatted_boolean = formatted(boolean(), MergedOptionStringFormatter, expected_type=bool)

        return create_spec(Harpoon
            , config = file_spec()

            , extra = defaulted(formatted_string, "")
            , chosen_task = defaulted(formatted_string, "list_tasks")
            , chosen_image = defaulted(formatted_string, "")

            , flat = defaulted(formatted_boolean, False)
            , no_cleanup = defaulted(formatted_boolean, False)
            , interactive = defaulted(formatted_boolean, True)
            , silent_build = defaulted(formatted_boolean, False)
            , keep_replaced = defaulted(formatted_boolean, False)
            , ignore_missing = defaulted(formatted_boolean, False)
            , no_intervention = defaulted(formatted_boolean, False)

            , do_push = defaulted(formatted_boolean, False)
            , only_pushable = defaulted(formatted_boolean, False)
            , docker_context = any_spec()
            )

