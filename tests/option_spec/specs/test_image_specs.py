# coding: spec

from harpoon.option_spec import image_specs as specs, image_objs as objs

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
from delfick_project.option_merge import MergedOptions
from delfick_project.norms import sb, dictobj, Meta
import mock

describe HarpoonCase, "Mount spec":
    before_each:
        self.meta = mock.Mock(name="meta", spec=Meta)
        self.local_path = self.unique_val()
        self.container_path = self.unique_val()
        self.array_format = [self.local_path, self.container_path]
        self.string_format = "{0}:{1}".format(*self.array_format)

    def check_paths(self, value):
        made = specs.mount_spec().normalise(self.meta, value)
        assert made.local_path == self.local_path
        assert made.container_path == self.container_path

    def check_permissions(self, value, expected):
        made = specs.mount_spec().normalise(self.meta, value)
        assert made.permissions == expected

    it "takes as [local_path, container_path]":
        self.check_paths(self.array_format)
        self.check_permissions(self.array_format, expected="rw")

    it "takes as [local_path, container_path, permissions]":
        self.check_paths(self.array_format + ["ro"])
        self.check_permissions(self.array_format + ["ro"], expected="ro")

    it "takes as local_path:container_path":
        self.check_paths(self.string_format)
        self.check_permissions(self.string_format, expected="rw")

    it "takes as local_path:container_path:permissions":
        self.check_paths(self.string_format + ":ro")
        self.check_permissions(self.string_format + ":ro", expected="ro")

describe HarpoonCase, "Env spec":
    before_each:
        self.meta = mock.Mock(name="meta", spec=Meta)
        self.env_name = self.unique_val()
        self.fallback_val = self.unique_val()

    it "takes in just the env_name":
        assert ":" not in self.env_name
        assert "=" not in self.env_name

        made = specs.env_spec().normalise(self.meta, self.env_name)
        assert made.env_name == self.env_name
        assert made.set_val == None
        assert made.default_val == None

    it "takes in env as a list with 1 item":
        assert ":" not in self.env_name
        assert "=" not in self.env_name

        made = specs.env_spec().normalise(self.meta, [self.env_name])
        assert made.env_name == self.env_name
        assert made.set_val == None
        assert made.default_val == None

    it "takes in env as a list with 2 items":
        assert ":" not in self.env_name
        assert "=" not in self.env_name

        made = specs.env_spec().normalise(self.meta, [self.env_name, self.fallback_val])
        assert made.env_name == self.env_name
        assert made.set_val == None
        assert made.default_val == self.fallback_val

    it "takes in env with blank default if suffixed with a colon":
        made = specs.env_spec().normalise(self.meta, self.env_name + ":")
        assert made.env_name == self.env_name
        assert made.set_val == None
        assert made.default_val == ""

    it "takes in env with blank set if suffixed with an equals sign":
        made = specs.env_spec().normalise(self.meta, self.env_name + "=")
        assert made.env_name == self.env_name
        assert made.set_val == ""
        assert made.default_val == None

    it "takes in default value if seperated by a colon":
        made = specs.env_spec().normalise(self.meta, self.env_name + ":" + self.fallback_val)
        assert made.env_name == self.env_name
        assert made.set_val == None
        assert made.default_val == self.fallback_val

    it "takes in set value if seperated by an equals sign":
        made = specs.env_spec().normalise(self.meta, self.env_name + "=" + self.fallback_val)
        assert made.env_name == self.env_name
        assert made.set_val == self.fallback_val
        assert made.default_val == None

describe HarpoonCase, "Link spec":
    before_each:

        class container_kls(dictobj):
            fields = ["container_name"]

        self.meta = mock.Mock(name="meta", spec=Meta)
        self.container_alias = self.unique_val()
        self.container = container_kls("somewhere.com/{0}".format(self.container_alias))
        self.converted_container_name = "somewhere.com-{0}".format(self.container_alias)
        self.meta.everything = MergedOptions.using(
            {"container": self.container}, dont_prefix=[dictobj]
        )

    def do_check(self, value, container, expected_alias):
        made = specs.link_spec().normalise(self.meta, value)
        assert made.container == container
        assert made.container_name == self.container.container_name
        assert made.link_name == expected_alias

    it "takes in as a list of 1 or two items":
        self.do_check(
            ["{container}"], container=self.container, expected_alias=self.converted_container_name
        )
        self.do_check(
            ["{container}", self.container_alias],
            container=self.container,
            expected_alias=self.container_alias,
        )

    it "takes in as a colon seperated list":
        self.do_check(
            "{{container}}:{0}".format(self.container_alias),
            container=self.container,
            expected_alias=self.container_alias,
        )

    it "doesn't need a container":
        self.do_check(
            "{0}:{1}".format(self.container.container_name, self.container_alias),
            container=None,
            expected_alias=self.container_alias,
        )
        self.do_check(
            [self.container.container_name, self.container_alias],
            container=None,
            expected_alias=self.container_alias,
        )

describe HarpoonCase, "Port spec":
    before_each:
        self.meta = mock.Mock(name="meta", spec=Meta)
        self.ip = self.unique_val()
        self.host_port = 80
        self.container_port = 70
        self.container_port_val = lambda transport: objs.ContainerPort(70, transport)

    def do_check(
        self, value, has_ip, has_host_port, has_container_port, expected_transport=sb.NotSpecified
    ):
        made = specs.port_spec().normalise(self.meta, value)

        if has_ip:
            assert made.ip == self.ip
        else:
            assert made.ip == sb.NotSpecified

        if has_host_port:
            assert made.host_port == self.host_port
        else:
            assert made.host_port == sb.NotSpecified

        if has_container_port:
            assert made.container_port == self.container_port_val(expected_transport)
        else:
            assert made.container_port == sb.NotSpecified

    it "takes as a list of 1 to 3 items":
        self.do_check(
            [self.container_port], has_ip=False, has_host_port=False, has_container_port=True
        )
        self.do_check(
            ["{0}/tcp".format(self.container_port)],
            has_ip=False,
            has_host_port=False,
            has_container_port=True,
            expected_transport="tcp",
        )

        self.do_check(
            [self.host_port, self.container_port],
            has_ip=False,
            has_host_port=True,
            has_container_port=True,
        )
        self.do_check(
            [self.ip, self.host_port, self.container_port],
            has_ip=True,
            has_host_port=True,
            has_container_port=True,
        )

    it "takes as a colon seperated list of 1 to 3 items":
        self.do_check(
            "{0}".format(self.container_port),
            has_ip=False,
            has_host_port=False,
            has_container_port=True,
        )
        self.do_check(
            "{0}/tcp".format(self.container_port),
            has_ip=False,
            has_host_port=False,
            has_container_port=True,
            expected_transport="tcp",
        )

        self.do_check(
            "{0}:{1}".format(self.host_port, self.container_port),
            has_ip=False,
            has_host_port=True,
            has_container_port=True,
        )

        self.do_check(
            "{0}:{1}:{2}".format(self.ip, self.host_port, self.container_port),
            has_ip=True,
            has_host_port=True,
            has_container_port=True,
        )
        self.do_check(
            "{0}::{1}".format(self.ip, self.container_port),
            has_ip=True,
            has_host_port=False,
            has_container_port=True,
        )
        self.do_check(
            "{0}::{1}/tcp".format(self.ip, self.container_port),
            has_ip=True,
            has_host_port=False,
            has_container_port=True,
            expected_transport="tcp",
        )

describe HarpoonCase, "Container Port Spec":
    before_each:
        self.meta = mock.Mock(name="meta", spec=Meta)

    it "defaults transport to sb.NotSpecified":
        assert specs.container_port_spec().normalise(self.meta, "80") == objs.ContainerPort(
            80, sb.NotSpecified
        )

    it "takes in transport as a string or as a list":
        assert specs.container_port_spec().normalise(self.meta, "80/tcp") == objs.ContainerPort(
            80, "tcp"
        )
        assert specs.container_port_spec().normalise(
            self.meta, ["80", "tcp"]
        ) == objs.ContainerPort(80, "tcp")
