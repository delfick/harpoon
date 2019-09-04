"""
Here we define the yaml specification for Harpoon options, task options and image
options.

The specifications are responsible for sanitation, validation and normalisation.
"""

from harpoon.option_spec.command_specs import command_spec
from harpoon.formatter import MergedOptionStringFormatter
from harpoon.option_spec.command_objs import Commands
from harpoon.option_spec import authentication_objs
from harpoon.ship.network import NetworkManager
from harpoon.helpers import memoized_property
from harpoon.option_spec import task_objs
from harpoon import helpers as hp

from delfick_project.norms import sb, dictobj, va
import sys


class Harpoon(dictobj):
    fields = {
        "tag": "Tag used for pulling/pushing a single image",
        "flat": "Don't show images as layers when doing ``harpoon show``",
        "extra": "Sets the ``$@`` variable. Alternatively specify these after a ``--`` on the commandline",
        "debug": "Whether debug has been specified",
        "stdout": "The stdout to use for printing",
        "config": "The location of the configuration to use. If not set the ``HARPOON_CONFIG`` env variable is used",
        "addons": "A dictionary of namespace to list of names for addons to register",
        "do_push": "Push images after making them (automatically set by the ``push`` tasks",
        "artifact": "Extra information for actions",
        "no_cleanup": "Don't cleanup the images/containers automatically after finish",
        "tty_stdin": "The stdin to use for a tty",
        "tty_stdout": "The stdout to use for a tty",
        "tty_stderr": "The stderr to use for a tty",
        "extra_files": "Extra files to load in as configuration",
        "chosen_task": "The task to run",
        "interactive": "Run the container with a tty",
        "chosen_image": "The image that we want to run",
        "silent_build": "Don't print out log information",
        "only_pushable": "Ignore images that don't have an ``image_index`` option",
        "keep_replaced": "Don't auto remove replaced images",
        "ignore_missing": "Don't raise errors if we try to pull an image that doesn't exist",
        "docker_context": "The docker context object (set internally)",
        "no_intervention": "Don't create intervention images when an image breaks",
        "intervene_afterwards": "Create an intervention image even if the image succeeds",
        "docker_context_maker": "Function that makes a new docker context object (set internally)",
    }

    @hp.memoized_property
    def network_manager(self):
        return NetworkManager(self.docker_api)

    @property
    def docker_api(self):
        return self.docker_context.api


class other_options(dictobj):
    fields = {
        "start": "Extra options to pass into docker.start",
        "create": "Extra options to pass into docker.create",
        "build": "Extra options to pass into docker.build",
        "host_config": "extra options to pass into docker.utils.host_config",
    }


class authentication_spec(sb.Spec):
    def normalise_filled(self, meta, value):
        # Make sure the value is a dictionary with a 'use' option
        sb.set_options(
            use=sb.required(sb.string_choice_spec(["kms", "plain", "s3_slip"]))
        ).normalise(meta, value)

        use = value["use"]
        formatted_string = sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)

        if use == "kms" or use == "plain":
            kls = (
                authentication_objs.PlainAuthentication
                if use == "plain"
                else authentication_objs.KmsAuthentication
            )
            spec = dict(
                username=sb.required(formatted_string), password=sb.required(formatted_string)
            )
            if use == "kms":
                spec.update(
                    role=sb.required(formatted_string), region=sb.required(formatted_string)
                )
        elif use == "s3_slip":
            kls = authentication_objs.S3SlipAuthentication
            spec = dict(role=sb.required(formatted_string), location=sb.required(formatted_string))

        return sb.create_spec(kls, **spec).normalise(meta, value)


class HarpoonSpec(object):
    """Knows about harpoon specific configuration"""

    @memoized_property
    def task_name_spec(self):
        """Just needs to be ascii"""
        return sb.valid_string_spec(va.no_whitespace(), va.regexed(r"^[a-zA-Z][a-zA-Z0-9-_\.]*$"))

    @memoized_property
    def container_name_spec(self):
        """Just needs to be ascii"""
        return sb.valid_string_spec(va.no_whitespace(), va.regexed(r"^[a-zA-Z][a-zA-Z0-9-_\.]*$"))

    def tasks_spec(self, available_actions, default_action="run"):
        """Tasks for a particular image"""
        # fmt: off
        return sb.dictof(
              self.task_name_spec
            , sb.create_spec(task_objs.Task, va.deprecated_key("spec", "Use ``action`` and ``options`` instead (note that ``action`` defaults to run)")
                , action = sb.defaulted(sb.string_choice_spec(available_actions, "No such task"), default_action)
                , options = sb.dictionary_spec()
                , overrides = sb.dictionary_spec()
                , description = sb.string_spec()
                )
            )
        # fmt: on

    @memoized_property
    def authentications_spec(self):
        """Spec for a group of authentication options"""
        # fmt: off
        return sb.container_spec(authentication_objs.Authentication
              , sb.dictof(sb.string_spec(), sb.set_options(
                  reading = sb.optional_spec(authentication_spec())
                , writing = sb.optional_spec(authentication_spec())
                )
              )
            )
        # fmt: on

    @memoized_property
    def wait_condition_spec(self):
        """Spec for a wait_condition block"""
        from harpoon.option_spec import image_objs

        formatted_string = sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)
        # fmt: off
        return sb.create_spec(image_objs.WaitCondition
            , harpoon = sb.formatted(sb.overridden("{harpoon}"), formatter=MergedOptionStringFormatter)
            , timeout = sb.defaulted(sb.integer_spec(), 300)
            , wait_between_attempts = sb.defaulted(sb.float_spec(), 5)

            , greps = sb.optional_spec(sb.dictof(formatted_string, formatted_string))
            , command = sb.optional_spec(sb.listof(formatted_string))
            , port_open = sb.optional_spec(sb.listof(sb.integer_spec()))
            , file_value = sb.optional_spec(sb.dictof(formatted_string, formatted_string))
            , curl_result = sb.optional_spec(sb.dictof(formatted_string, formatted_string))
            , file_exists = sb.optional_spec(sb.listof(formatted_string))
            )
        # fmt: on

    @memoized_property
    def context_spec(self):
        """Spec for specifying context options"""
        from harpoon.option_spec import image_objs

        # fmt: off
        return sb.dict_from_bool_spec(lambda meta, val: {"enabled": val}
            , sb.create_spec(image_objs.Context
                , va.deprecated_key("use_git_timestamps", "Since docker 1.8, timestamps no longer invalidate the docker layer cache")

                , include = sb.listof(sb.string_spec())
                , exclude = sb.listof(sb.string_spec())
                , enabled = sb.defaulted(sb.boolean(), True)
                , find_options = sb.string_spec()

                , parent_dir = sb.directory_spec(sb.formatted(sb.defaulted(sb.string_spec(), "{config_root}"), formatter=MergedOptionStringFormatter))
                , use_gitignore = sb.defaulted(sb.boolean(), False)
                , ignore_find_errors = sb.defaulted(sb.boolean(), False)
                )
            )
        # fmt: on

    @memoized_property
    def image_spec(self):
        """Spec for each image"""
        from harpoon.option_spec import image_specs as specs
        from harpoon.option_spec import image_objs

        class persistence_shell_spec(sb.Spec):
            """Make the persistence shell default to the shell on the image"""

            def normalise(self, meta, val):
                shell = sb.defaulted(sb.string_spec(), "/bin/bash").normalise(
                    meta,
                    meta.everything[["images", meta.key_names()["_key_name_2"]]].get(
                        "shell", sb.NotSpecified
                    ),
                )
                shell = sb.defaulted(
                    sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter), shell
                ).normalise(meta, val)
                return shell

        # fmt: off
        return sb.create_spec(image_objs.Image
            , va.deprecated_key("persistence", "The persistence feature has been removed")
            , va.deprecated_key("squash_after", "The squash feature has been removed")
            , va.deprecated_key("squash_before_push", "The squash feature has been removed")

            # Changed how volumes_from works
            , va.deprecated_key("volumes_from", "Use ``volumes.share_with``")

            # Deprecated link
            , va.deprecated_key("link", "Use ``links``")

            # Harpoon options
            , harpoon = sb.any_spec()

            # default the name to the key of the image
            , tag = sb.optional_spec(sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter))
            , name = sb.formatted(sb.defaulted(sb.string_spec(), "{_key_name_1}"), formatter=MergedOptionStringFormatter)
            , key_name = sb.formatted(sb.overridden("{_key_name_1}"), formatter=MergedOptionStringFormatter)
            , image_name = sb.optional_spec(sb.string_spec())
            , image_index = sb.formatted(sb.defaulted(sb.string_spec(), ""), formatter=MergedOptionStringFormatter)
            , container_name = sb.optional_spec(sb.string_spec())
            , image_name_prefix = sb.defaulted(sb.string_spec(), "")

            , no_tty_option = sb.defaulted(sb.formatted(sb.boolean(), formatter=MergedOptionStringFormatter), False)

            , user = sb.defaulted(sb.string_spec(), None)
            , configuration = sb.any_spec()

            , vars = sb.dictionary_spec()
            , assume_role = sb.optional_spec(sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter))
            , deleteable_image = sb.defaulted(sb.boolean(), False)

            , authentication = self.authentications_spec

            # The spec itself
            , shell = sb.defaulted(sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter), "/bin/bash")
            , bash = sb.delayed(sb.optional_spec(sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)))
            , command = sb.delayed(sb.optional_spec(sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter)))
            , commands = sb.required(sb.container_spec(Commands, sb.listof(command_spec())))
            , cache_from = sb.delayed(sb.or_spec(sb.boolean(), sb.listof(sb.formatted(sb.string_spec(), formatter=MergedOptionStringFormatter))))
            , cleanup_intermediate_images = sb.defaulted(sb.boolean(), True)

            , links = sb.listof(specs.link_spec(), expect=image_objs.Link)

            , context = self.context_spec
            , wait_condition = sb.optional_spec(self.wait_condition_spec)

            , lxc_conf = sb.defaulted(sb.filename_spec(), None)

            , volumes = sb.create_spec(image_objs.Volumes
                , mount = sb.listof(specs.mount_spec(), expect=image_objs.Mount)
                , share_with = sb.listof(sb.formatted(sb.string_spec(), MergedOptionStringFormatter, expected_type=image_objs.Image))
                )

            , dependency_options = sb.dictof(specs.image_name_spec()
                , sb.create_spec(image_objs.DependencyOptions
                  , attached = sb.defaulted(sb.boolean(), False)
                  , wait_condition = sb.optional_spec(self.wait_condition_spec)
                  )
                )

            , env = sb.listof(specs.env_spec(), expect=image_objs.Environment)
            , ports = sb.listof(specs.port_spec(), expect=image_objs.Port)
            , ulimits = sb.defaulted(sb.listof(sb.dictionary_spec()), None)
            , log_config = sb.defaulted(sb.listof(sb.dictionary_spec()), None)
            , security_opt = sb.defaulted(sb.listof(sb.string_spec()), None)
            , read_only_rootfs = sb.defaulted(sb.boolean(), False)

            , other_options = sb.create_spec(other_options
                , start = sb.dictionary_spec()
                , build = sb.dictionary_spec()
                , create = sb.dictionary_spec()
                , host_config = sb.dictionary_spec()
                )

            , network = sb.create_spec(image_objs.Network
                , dns = sb.defaulted(sb.listof(sb.string_spec()), None)
                , mode = sb.defaulted(sb.string_spec(), None)
                , hostname = sb.defaulted(sb.string_spec(), None)
                , domainname = sb.defaulted(sb.string_spec(), None)
                , disabled = sb.defaulted(sb.boolean(), False)
                , dns_search = sb.defaulted(sb.listof(sb.string_spec()), None)
                , extra_hosts = sb.listof(sb.string_spec())
                , network_mode = sb.defaulted(sb.string_spec(), None)
                , publish_all_ports = sb.defaulted(sb.boolean(), False)
                )

            , cpu = sb.create_spec(image_objs.Cpu
                , cap_add = sb.defaulted(sb.listof(sb.string_spec()), None)
                , cpuset_cpus = sb.defaulted(sb.string_spec(), None)
                , cpuset_mems = sb.defaulted(sb.string_spec(), None)
                , cap_drop = sb.defaulted(sb.listof(sb.string_spec()), None)
                , mem_limit = sb.defaulted(sb.integer_spec(), 0)
                , cpu_shares = sb.defaulted(sb.integer_spec(), None)
                , memswap_limit = sb.defaulted(sb.integer_spec(), 0)
                )

            , devices = sb.defaulted(sb.listof(sb.dictionary_spec()), None)
            , privileged = sb.defaulted(sb.boolean(), False)
            , restart_policy = sb.defaulted(sb.string_spec(), None)
            )
        # fmt: on

    @memoized_property
    def harpoon_spec(self):
        """Spec for harpoon options"""
        formatted_string = sb.formatted(
            sb.string_spec(), MergedOptionStringFormatter, expected_type=str
        )
        formatted_boolean = sb.formatted(
            sb.boolean(), MergedOptionStringFormatter, expected_type=bool
        )

        # fmt: off
        return sb.create_spec(Harpoon
            , config = sb.optional_spec(sb.file_spec())

            , tag = sb.optional_spec(sb.string_spec())
            , extra = sb.defaulted(formatted_string, "")
            , debug = sb.defaulted(sb.boolean(), False)
            , addons = sb.dictof(sb.string_spec(), sb.listof(sb.string_spec()))
            , artifact = sb.optional_spec(formatted_string)
            , extra_files = sb.listof(sb.string_spec())
            , chosen_task = sb.defaulted(formatted_string, "list_tasks")
            , chosen_image = sb.defaulted(formatted_string, "")

            , flat = sb.defaulted(formatted_boolean, False)
            , no_cleanup = sb.defaulted(formatted_boolean, False)
            , interactive = sb.defaulted(formatted_boolean, True)
            , silent_build = sb.defaulted(formatted_boolean, False)
            , keep_replaced = sb.defaulted(formatted_boolean, False)
            , ignore_missing = sb.defaulted(formatted_boolean, False)
            , no_intervention = sb.defaulted(formatted_boolean, False)
            , intervene_afterwards = sb.defaulted(formatted_boolean, False)

            , do_push = sb.defaulted(formatted_boolean, False)
            , only_pushable = sb.defaulted(formatted_boolean, False)
            , docker_context = sb.any_spec()
            , docker_context_maker = sb.any_spec()

            , stdout = sb.defaulted(sb.any_spec(), sys.stdout)
            , tty_stdin = sb.defaulted(sb.any_spec(), None)
            , tty_stdout = sb.defaulted(sb.any_spec(), lambda: sys.stdout)
            , tty_stderr = sb.defaulted(sb.any_spec(), lambda: sys.stderr)
            )
        # fmt: on
