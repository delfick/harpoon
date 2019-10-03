# coding: spec

from harpoon.option_spec import image_specs as specs, image_objs as objs

from tests.helpers import HarpoonCase

from delfick_project.option_merge import MergedOptions
from delfick_project.norms import sb, dictobj, Meta
from unittest import mock
import pytest


@pytest.fixture()
def meta():
    return Meta.empty()


describe HarpoonCase, "Mount spec":

    @pytest.fixture()
    def M(self):
        class Mocks:
            local_path = self.unique_val()
            container_path = self.unique_val()

        Mocks.array_format = [Mocks.local_path, Mocks.container_path]
        Mocks.string_format = "{0}:{1}".format(*Mocks.array_format)
        return Mocks

    @pytest.fixture()
    def check_paths(self, meta, M):
        def check_paths(value):
            made = specs.mount_spec().normalise(meta, value)
            assert made.local_path == M.local_path
            assert made.container_path == M.container_path

        return check_paths

    @pytest.fixture()
    def check_permissions(self, meta):
        def check_permissions(value, expected):
            made = specs.mount_spec().normalise(meta, value)
            assert made.permissions == expected

        return check_permissions

    it "takes as [local_path, container_path]", check_paths, check_permissions, M:
        check_paths(M.array_format)
        check_permissions(M.array_format, expected="rw")

    it "takes as [local_path, container_path, permissions]", check_paths, check_permissions, M:
        check_paths(M.array_format + ["ro"])
        check_permissions(M.array_format + ["ro"], expected="ro")

    it "takes as local_path:container_path", check_paths, check_permissions, M:
        check_paths(M.string_format)
        check_permissions(M.string_format, expected="rw")

    it "takes as local_path:container_path:permissions", check_paths, check_permissions, M:
        check_paths(M.string_format + ":ro")
        check_permissions(M.string_format + ":ro", expected="ro")

describe HarpoonCase, "Env spec":

    @pytest.fixture()
    def M(self):
        class Mocks:
            env_name = self.unique_val()
            fallback_val = self.unique_val()

        return Mocks

    it "takes in just the env_name", M, meta:
        assert ":" not in M.env_name
        assert "=" not in M.env_name

        made = specs.env_spec().normalise(meta, M.env_name)
        assert made.env_name == M.env_name
        assert made.set_val == None
        assert made.default_val == None

    it "takes in env as a list with 1 item", M, meta:
        assert ":" not in M.env_name
        assert "=" not in M.env_name

        made = specs.env_spec().normalise(meta, [M.env_name])
        assert made.env_name == M.env_name
        assert made.set_val == None
        assert made.default_val == None

    it "takes in env as a list with 2 items", M, meta:
        assert ":" not in M.env_name
        assert "=" not in M.env_name

        made = specs.env_spec().normalise(meta, [M.env_name, M.fallback_val])
        assert made.env_name == M.env_name
        assert made.set_val == None
        assert made.default_val == M.fallback_val

    it "takes in env with blank default if suffixed with a colon", M, meta:
        made = specs.env_spec().normalise(meta, M.env_name + ":")
        assert made.env_name == M.env_name
        assert made.set_val == None
        assert made.default_val == ""

    it "takes in env with blank set if suffixed with an equals sign", M, meta:
        made = specs.env_spec().normalise(meta, M.env_name + "=")
        assert made.env_name == M.env_name
        assert made.set_val == ""
        assert made.default_val == None

    it "takes in default value if seperated by a colon", M, meta:
        made = specs.env_spec().normalise(meta, M.env_name + ":" + M.fallback_val)
        assert made.env_name == M.env_name
        assert made.set_val == None
        assert made.default_val == M.fallback_val

    it "takes in set value if seperated by an equals sign", M, meta:
        made = specs.env_spec().normalise(meta, M.env_name + "=" + M.fallback_val)
        assert made.env_name == M.env_name
        assert made.set_val == M.fallback_val
        assert made.default_val == None

describe HarpoonCase, "Link spec":

    @pytest.fixture()
    def container_alias(self):
        return self.unique_val()

    @pytest.fixture()
    def converted_container_name(self, container_alias):
        return "somewhere.com-{0}".format(container_alias)

    @pytest.fixture()
    def container(self, container_alias):
        class C(dictobj):
            fields = ["container_name"]

        return C("somewhere.com/{0}".format(container_alias))

    @pytest.fixture()
    def meta(self, container):
        return Meta(MergedOptions.using({"container": container}, dont_prefix=[dictobj]), [])

    @pytest.fixture()
    def assertLinks(self, meta, container):
        def assertLinks(value, *, expected_alias, no_container=False, container_name=None):
            made = specs.link_spec().normalise(meta, value)

            if no_container:
                assert made.container is None
            else:
                assert made.container == container

            if container_name:
                assert made.container_name == container_name
            else:
                assert made.container_name == container.container_name

            assert made.link_name == expected_alias

        return assertLinks

    it "takes in as a list of 1 or two items", assertLinks, converted_container_name, container_alias:
        assertLinks(["{container}"], expected_alias=converted_container_name)
        assertLinks(["{container}", container_alias], expected_alias=container_alias)

    it "takes in as a colon seperated list", assertLinks, container_alias:
        assertLinks("{{container}}:{0}".format(container_alias), expected_alias=container_alias)

    it "doesn't need a container", assertLinks, container, container_alias:
        assertLinks(
            "{0}:{1}".format(container.container_name, container_alias),
            no_container=True,
            container_name=container.container_name,
            expected_alias=container_alias,
        )
        assertLinks(
            [container.container_name, container_alias],
            no_container=True,
            container_name=container.container_name,
            expected_alias=container_alias,
        )

describe HarpoonCase, "Port spec":

    @pytest.fixture()
    def M(self):
        class Mocks:
            ip = self.unique_val()
            host_port = 80
            container_port = 70
            container_port_val = lambda transport: objs.ContainerPort(70, transport)

        return Mocks

    @pytest.fixture()
    def assertPorts(self, meta, M):
        def assertPorts(
            value, has_ip, has_host_port, has_container_port, expected_transport=sb.NotSpecified
        ):
            made = specs.port_spec().normalise(meta, value)

            if has_ip:
                assert made.ip == M.ip
            else:
                assert made.ip == sb.NotSpecified

            if has_host_port:
                assert made.host_port == M.host_port
            else:
                assert made.host_port == sb.NotSpecified

            if has_container_port:
                assert made.container_port == M.container_port_val(expected_transport)
            else:
                assert made.container_port == sb.NotSpecified

        return assertPorts

    it "takes as a list of 1 to 3 items", assertPorts, M:
        assertPorts([M.container_port], has_ip=False, has_host_port=False, has_container_port=True)
        assertPorts(
            ["{0}/tcp".format(M.container_port)],
            has_ip=False,
            has_host_port=False,
            has_container_port=True,
            expected_transport="tcp",
        )

        assertPorts(
            [M.host_port, M.container_port],
            has_ip=False,
            has_host_port=True,
            has_container_port=True,
        )
        assertPorts(
            [M.ip, M.host_port, M.container_port],
            has_ip=True,
            has_host_port=True,
            has_container_port=True,
        )

    it "takes as a colon seperated list of 1 to 3 items", assertPorts, M:
        assertPorts(
            "{0}".format(M.container_port),
            has_ip=False,
            has_host_port=False,
            has_container_port=True,
        )
        assertPorts(
            "{0}/tcp".format(M.container_port),
            has_ip=False,
            has_host_port=False,
            has_container_port=True,
            expected_transport="tcp",
        )

        assertPorts(
            "{0}:{1}".format(M.host_port, M.container_port),
            has_ip=False,
            has_host_port=True,
            has_container_port=True,
        )

        assertPorts(
            "{0}:{1}:{2}".format(M.ip, M.host_port, M.container_port),
            has_ip=True,
            has_host_port=True,
            has_container_port=True,
        )
        assertPorts(
            "{0}::{1}".format(M.ip, M.container_port),
            has_ip=True,
            has_host_port=False,
            has_container_port=True,
        )
        assertPorts(
            "{0}::{1}/tcp".format(M.ip, M.container_port),
            has_ip=True,
            has_host_port=False,
            has_container_port=True,
            expected_transport="tcp",
        )

describe HarpoonCase, "Container Port Spec":
    it "defaults transport to sb.NotSpecified", meta:
        assert specs.container_port_spec().normalise(meta, "80") == objs.ContainerPort(
            80, sb.NotSpecified
        )

    it "takes in transport as a string or as a list", meta:
        assert specs.container_port_spec().normalise(meta, "80/tcp") == objs.ContainerPort(
            80, "tcp"
        )
        assert specs.container_port_spec().normalise(meta, ["80", "tcp"]) == objs.ContainerPort(
            80, "tcp"
        )
