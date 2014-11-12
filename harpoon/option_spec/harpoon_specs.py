from input_algorithms.spec_base import (
      create_spec, defaulted, string_choice_spec
    , dictionary_spec, string_spec, valid_string_spec, dictof, set_options, dict_from_bool_spec
    , listof, optional_spec, or_spec
    , directory_spec, filename_spec
    , boolean, required, formatted, overridden
    )

from harpoon.option_spec.image_specs import command_spec, link_spec, mount_spec, env_spec, port_spec
from harpoon.formatter import MergedOptionStringFormatter

from harpoon.option_spec import task_objs, image_objs
from harpoon.helpers import memoized_property
from input_algorithms import validators

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
        return create_spec(image_objs.Image
            # Change the context options
            , validators.deprecated_key("exclude_context", "Use ``context.exclude``")
            , validators.deprecated_key("use_git_timestamps", "Use ``context.use_git_timestamps``")
            , validators.deprecated_key("respect_gitignore", "Use ``context.use_gitignore``")
            , validators.deprecated_key("parent_dir", "Use ``context.parent_dir``")

            # Changed how volumes_from works
            , validators.deprecated_key("volumes_from", "Use ``volumes.share_with``")

            # default the name to the key of the image
            , name = formatted(defaulted(string_spec(), "{_key_name}"), formatter=MergedOptionStringFormatter)
            , key_name = formatted(overridden("{_key_name}"), formatter=MergedOptionStringFormatter)
            , image_name = formatted(overridden("{harpoon.image_names.{this.name}}"), formatter=MergedOptionStringFormatter)
            , container_name = formatted(overridden("{harpoon.container_names.{this.name}}"), formatter=MergedOptionStringFormatter)

            # The spec itself
            , commands = required(listof(command_spec(), expect=image_objs.Command))
            , links = listof(link_spec(), expect=image_objs.Link)

            , context = dict_from_bool_spec(lambda meta, val: {"enabled": val}
                , create_spec(image_objs.Context
                    , include = listof(string_spec())
                    , exclude = listof(string_spec())
                    , enabled = defaulted(boolean(), True)

                    , parent_dir = optional_spec(directory_spec())
                    , use_gitignore = defaulted(boolean(), True)
                    , use_git_timestamps = defaulted(or_spec(boolean(), listof(string_spec())), False)
                    )
                )

            , lxc_conf = filename_spec()

            , volumes = create_spec(image_objs.Volumes
                , mount = listof(mount_spec(), expect=image_objs.Mount)
                , share_with = listof(formatted(string_spec(), MergedOptionStringFormatter, expected_type=image_objs.Image))
                )

            , dependency_options = dictof(self.image_name_spec
                , create_spec(image_objs.DependencyOptions
                  , attached = defaulted(boolean(), False)
                  )
                )

            , env = listof(env_spec(), expect=image_objs.Environment)
            , ports = listof(port_spec(), expect=image_objs.Port)

            , other_options = set_options(
                  build = dictionary_spec()
                , run = dictionary_spec()
                )

            , network = create_spec(image_objs.Network
                , dns = optional_spec(listof(string_spec()))
                , mode = optional_spec(string_spec())
                , hostname = optional_spec(string_spec())
                , disabled = defaulted(boolean(), False)
                , dns_search = optional_spec(listof(string_spec()))
                , publish_all_ports = optional_spec(boolean())
                )

            , privileged = defaulted(boolean, False)
            )

