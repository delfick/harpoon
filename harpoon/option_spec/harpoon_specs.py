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
    , container_spec, many_format, delayed
    , float_spec, Spec, set_options
    )

from harpoon.option_spec.command_specs import command_spec
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.option_spec.command_objs import Commands
from harpoon.option_spec import authentication_objs
from harpoon.helpers import memoized_property
from harpoon.option_spec import task_objs

from input_algorithms.dictobj import dictobj
from input_algorithms import validators

import time
import six
import sys

class Harpoon(dictobj):
    fields = {
          "flat": "Don't show images as layers when doing ``harpoon show``"
        , "extra": "Sets the ``$@`` variable. Alternatively specify these after a ``--`` on the commandline"
        , "debug": "Whether debug has been specified"
        , "stdout": "The stdout to use for printing"
        , "config": "The location of the configuration to use. If not set the ``HARPOON_CONFIG`` env variable is used"
        , "do_push": "Push images after making them (automatically set by the ``push`` tasks"
        , "artifact": "Extra information for actions"
        , "no_cleanup": "Don't cleanup the images/containers automatically after finish"
        , "tty_stdin": "The stdin to use for a tty"
        , "tty_stdout": "The stdout to use for a tty"
        , "tty_stderr": "The stderr to use for a tty"
        , "chosen_task": "The task to run"
        , "interactive": "Run the container with a tty"
        , "chosen_image": "The image that we want to run"
        , "silent_build": "Don't print out log information"
        , "only_pushable": "Ignore images that don't have an ``image_index`` option"
        , "keep_replaced": "Don't auto remove replaced images"
        , "ignore_missing": "Don't raise errors if we try to pull an image that doesn't exist"
        , "docker_context": "The docker context object (set internally)"
        , "no_intervention": "Don't create intervention images when an image breaks"
        , "intervene_afterwards": "Create an intervention image even if the image succeeds"
        , "docker_context_maker": "Function that makes a new docker context object (set internally)"
        }

class other_options(dictobj):
    fields = {
          "start": "Extra options to pass into docker.start"
        , "create": "Extra options to pass into docker.create"
        , "build": "Extra options to pass into docker.build"
        , "host_config": "extra options to pass into docker.utils.host_config"
        }

class authentication_spec(Spec):
    def normalise_filled(self, meta, value):
        # Make sure the value is a dictionary with a 'use' option
        set_options(use=required(string_choice_spec(["kms", "plain", "s3_slip"]))).normalise(meta, value)

        use = value["use"]
        formatted_string = formatted(string_spec(), formatter=MergedOptionStringFormatter)

        if use == "kms" or use == "plain" :
            kls = authentication_objs.PlainAuthentication if use == "plain" else authentication_objs.KmsAuthentication
            spec = dict(username=required(formatted_string), password=required(formatted_string))
            if use == "kms":
                spec.update(role=required(formatted_string), region=required(formatted_string))
        elif use == "s3_slip":
            kls = authentication_objs.S3SlipAuthentication
            spec = dict(role=required(formatted_string), location=required(formatted_string))

        return create_spec(kls, **spec).normalise(meta, value)

class HarpoonSpec(object):
    """Knows about harpoon specific configuration"""

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
    def authentications_spec(self):
        """Spec for a group of authentication options"""
        return optional_spec(container_spec(authentication_objs.Authentication
                , dictof(string_spec(), set_options(
                      reading = optional_spec(authentication_spec())
                    , writing = optional_spec(authentication_spec())
                    )
                ))
            )

    @memoized_property
    def wait_condition_spec(self):
        """Spec for a wait_condition block"""
        from harpoon.option_spec import image_objs
        formatted_string = formatted(string_spec(), formatter=MergedOptionStringFormatter)
        return create_spec(image_objs.WaitCondition
            , harpoon = formatted(overridden("{harpoon}"), formatter=MergedOptionStringFormatter)
            , timeout = defaulted(integer_spec(), 300)
            , wait_between_attempts = defaulted(float_spec(), 5)

            , greps = optional_spec(dictof(formatted_string, formatted_string))
            , command = optional_spec(listof(formatted_string))
            , port_open = optional_spec(listof(integer_spec()))
            , file_value = optional_spec(dictof(formatted_string, formatted_string))
            , curl_result = optional_spec(dictof(formatted_string, formatted_string))
            , file_exists = optional_spec(listof(formatted_string))
            )

    @memoized_property
    def context_spec(self):
        """Spec for specifying context options"""
        from harpoon.option_spec import image_objs
        return dict_from_bool_spec(lambda meta, val: {"enabled": val}
            , create_spec(image_objs.Context
                , include = listof(string_spec())
                , exclude = listof(string_spec())
                , enabled = defaulted(boolean(), True)

                , parent_dir = directory_spec(formatted(defaulted(string_spec(), "{config_root}"), formatter=MergedOptionStringFormatter))
                , use_gitignore = defaulted(boolean(), False)
                , use_git_timestamps = defaulted(or_spec(boolean(), listof(string_spec())), False)
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
            , validators.deprecated_key("recursive", "Use ``persistence``")

            # Changed how volumes_from works
            , validators.deprecated_key("volumes_from", "Use ``volumes.share_with``")

            # Deprecated link
            , validators.deprecated_key("link", "Use ``links``")

            # Harpoon options
            , harpoon = any_spec()

            # default the name to the key of the image
            , tag = optional_spec(formatted(string_spec(), formatter=MergedOptionStringFormatter))
            , name = formatted(defaulted(string_spec(), "{_key_name_1}"), formatter=MergedOptionStringFormatter)
            , key_name = formatted(overridden("{_key_name_1}"), formatter=MergedOptionStringFormatter)
            , image_name = optional_spec(string_spec())
            , image_index = defaulted(string_spec(), "")
            , container_name = optional_spec(string_spec())
            , image_name_prefix = defaulted(string_spec(), "")

            , no_tty_option = defaulted(formatted(boolean(), formatter=MergedOptionStringFormatter), False)

            , user = defaulted(string_spec(), None)
            , mtime = defaulted(any_spec(), time.time())
            , configuration = any_spec()

            , vars = dictionary_spec()
            , assume_role = optional_spec(formatted(string_spec(), formatter=MergedOptionStringFormatter))
            , deleteable_image = defaulted(boolean(), False)

            , authentication = self.authentications_spec

            # The spec itself
            , bash = delayed(optional_spec(formatted(string_spec(), formatter=MergedOptionStringFormatter)))
            , command = delayed(optional_spec(formatted(string_spec(), formatter=MergedOptionStringFormatter)))
            , commands = required(container_spec(Commands, listof(command_spec())))
            , squash_after = optional_spec(or_spec(boolean(), container_spec(Commands, listof(command_spec()))))
            , squash_before_push = optional_spec(or_spec(boolean(), container_spec(Commands, listof(command_spec()))))
            , persistence = optional_spec(create_spec(image_objs.Persistence
                , validators.deprecated_key("persist", "Use ``folders``")
                , action = required(formatted(string_spec(), formatter=MergedOptionStringFormatter))
                , folders = required(listof(formatted(string_spec(), formatter=MergedOptionStringFormatter)))
                , cmd = optional_spec(formatted(string_spec(), formatter=MergedOptionStringFormatter))
                , shell = defaulted(formatted(string_spec(), formatter=MergedOptionStringFormatter), "/bin/bash")
                , no_volumes = defaulted(boolean(), False)
                , image_name = delayed(many_format(overridden("images.{_key_name_2}.image_name"), formatter=MergedOptionStringFormatter))
                ))

            , links = listof(specs.link_spec(), expect=image_objs.Link)

            , context = self.context_spec
            , wait_condition = optional_spec(self.wait_condition_spec)

            , lxc_conf = defaulted(filename_spec(), None)

            , volumes = create_spec(image_objs.Volumes
                , mount = listof(specs.mount_spec(), expect=image_objs.Mount)
                , share_with = listof(formatted(string_spec(), MergedOptionStringFormatter, expected_type=image_objs.Image))
                )

            , dependency_options = dictof(specs.image_name_spec()
                , create_spec(image_objs.DependencyOptions
                  , attached = defaulted(boolean(), False)
                  , wait_condition = optional_spec(self.wait_condition_spec)
                  )
                )

            , env = listof(specs.env_spec(), expect=image_objs.Environment)
            , ports = listof(specs.port_spec(), expect=image_objs.Port)
            , ulimits = defaulted(listof(dictionary_spec()), None)
            , log_config = defaulted(listof(dictionary_spec()), None)
            , security_opt = defaulted(listof(string_spec()), None)
            , read_only_rootfs = defaulted(boolean(), False)

            , other_options = create_spec(other_options
                , start = dictionary_spec()
                , build = dictionary_spec()
                , create = dictionary_spec()
                , host_config = dictionary_spec()
                )

            , network = create_spec(image_objs.Network
                , dns = defaulted(listof(string_spec()), None)
                , mode = defaulted(string_spec(), None)
                , hostname = defaulted(string_spec(), None)
                , domainname = defaulted(string_spec(), None)
                , disabled = defaulted(boolean(), False)
                , dns_search = defaulted(listof(string_spec()), None)
                , extra_hosts = listof(string_spec())
                , network_mode = defaulted(string_spec(), None)
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

            , devices = defaulted(listof(dictionary_spec()), None)
            , privileged = defaulted(boolean(), False)
            , restart_policy = defaulted(string_spec(), None)
            )

    @memoized_property
    def harpoon_spec(self):
        """Spec for harpoon options"""
        formatted_string = formatted(string_spec(), MergedOptionStringFormatter, expected_type=six.string_types)
        formatted_boolean = formatted(boolean(), MergedOptionStringFormatter, expected_type=bool)

        return create_spec(Harpoon
            , config = optional_spec(file_spec())

            , extra = defaulted(formatted_string, "")
            , debug = defaulted(boolean(), False)
            , artifact = optional_spec(formatted_string)
            , chosen_task = defaulted(formatted_string, "list_tasks")
            , chosen_image = defaulted(formatted_string, "")

            , flat = defaulted(formatted_boolean, False)
            , no_cleanup = defaulted(formatted_boolean, False)
            , interactive = defaulted(formatted_boolean, True)
            , silent_build = defaulted(formatted_boolean, False)
            , keep_replaced = defaulted(formatted_boolean, False)
            , ignore_missing = defaulted(formatted_boolean, False)
            , no_intervention = defaulted(formatted_boolean, False)
            , intervene_afterwards = defaulted(formatted_boolean, False)

            , do_push = defaulted(formatted_boolean, False)
            , only_pushable = defaulted(formatted_boolean, False)
            , docker_context = any_spec()
            , docker_context_maker = any_spec()

            , stdout = defaulted(any_spec(), sys.stdout)
            , tty_stdin = defaulted(any_spec(), None)
            , tty_stdout = defaulted(any_spec(), lambda: sys.stdout)
            , tty_stderr = defaulted(any_spec(), lambda: sys.stderr)
            )

