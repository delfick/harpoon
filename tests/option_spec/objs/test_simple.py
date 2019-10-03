# coding: spec

from harpoon.option_spec import image_objs as objs
from harpoon.errors import HarpoonError

from tests.helpers import HarpoonCase

from delfick_project.errors_pytest import assertRaises
from delfick_project.norms import sb
from unittest import mock
import pytest
import os

describe HarpoonCase, "Context object":

    @pytest.fixture()
    def parent_dir(self):
        return self.unique_val()

    it "defaults _use_gitignore and to sb.NotSpecified an include and exclude to None", parent_dir:
        enabled = mock.Mock(name="enabled")
        ctxt = objs.Context(enabled=enabled, parent_dir=parent_dir)
        assert ctxt.enabled is enabled
        assert ctxt.parent_dir == os.path.abspath(parent_dir)
        assert ctxt.include is None
        assert ctxt.exclude is None
        assert ctxt._use_gitignore is sb.NotSpecified

    describe "use_gitignore":
        it "returns False if _use_gitignore is sb.NotSpecified", parent_dir:
            ctxt = objs.Context(enabled=True, parent_dir=parent_dir)
            assert ctxt.use_gitignore is False

        it "returns the value of _use_gitignore otherwise", parent_dir:
            ctxt = objs.Context(enabled=True, parent_dir=parent_dir)
            ugi = mock.Mock(name="use_gitignore")
            ctxt.use_gitignore = ugi
            assert ctxt.use_gitignore is ugi

            ctxt = objs.Context(use_gitignore=ugi, enabled=True, parent_dir=parent_dir)
            assert ctxt.use_gitignore is ugi

    describe "parent_dir":
        it "gets set as the abspath of the value":
            enabled = mock.Mock(name="enabled")
            parent_dir = mock.Mock(name="parent_dir")
            abs_parent_dir = mock.Mock(name="abs_parent_dir")
            with mock.patch("os.path.abspath") as fake_abspath:
                fake_abspath.return_value = abs_parent_dir
                assert (
                    objs.Context(enabled=enabled, parent_dir=parent_dir).parent_dir
                    is abs_parent_dir
                )
                fake_abspath.assert_called_once_with(parent_dir)

    describe "git_root":
        it "goes up directories till it finds the .git folder":
            enabled = mock.Mock(name="enabled")
            with self.a_temp_dir() as directory:
                parent_dir = os.path.join(directory, "blah", ".git", "meh", "stuff")
                os.makedirs(parent_dir)
                assert objs.Context(
                    enabled=enabled, parent_dir=parent_dir
                ).git_root == os.path.abspath(os.path.join(directory, "blah"))

        it "complains if it can't find a .git folder":
            enabled = mock.Mock(name="enabled")
            with self.a_temp_dir() as directory:
                nxt = directory
                while nxt != "/" and not os.path.exists(os.path.join(nxt, ".git")):
                    nxt = os.path.dirname(nxt)
                assert not os.path.exists(os.path.join(nxt, ".git"))

                with assertRaises(HarpoonError, "Couldn't find a .git folder", start_at=directory):
                    objs.Context(enabled=enabled, parent_dir=directory).git_root

describe HarpoonCase, "Link object":
    it "Has a pair property returning container_name and link_name":
        container = mock.Mock(name="container")
        link_name = mock.Mock(name="link_name")
        container_name = mock.Mock(name="container_name")
        link = objs.Link(container, container_name, link_name)
        assert link.pair == (container_name, link_name)

describe HarpoonCase, "Volume object":
    describe "share_with_names":
        it "returns container_name of non string containers":
            cn1 = mock.Mock(name="cn1")
            cn2 = mock.Mock(name="cn2")

            c1 = mock.Mock(name="c1", spec=objs.Image, container_name=cn1)
            c2 = mock.Mock(name="c2", spec=objs.Image, container_name=cn2)

            volumes = objs.Volumes(mount=[], share_with=[c1, c2])
            assert list(volumes.share_with_names) == [cn1, cn2]

        it "returns container as is if a string":
            container1 = self.unique_val()
            container2 = self.unique_val()
            volumes = objs.Volumes(mount=[], share_with=[container1, container2])
            assert list(volumes.share_with_names) == [container1, container2]

        it "copes with mixed strings and container objects":
            cn2 = mock.Mock(name="cn2")
            container1 = self.unique_val()
            container2 = mock.Mock(name="container2", spec=objs.Image, container_name=cn2)

            volumes = objs.Volumes(mount=[], share_with=[container1, container2])
            assert list(volumes.share_with_names) == [container1, cn2]

    describe "volume_names":
        it "returns the container_path for each mount":
            cp1 = mock.Mock(name="cp1")
            cp2 = mock.Mock(name="cp2")
            m1 = mock.Mock(name="m1", spec=objs.Mount, container_path=cp1)
            m2 = mock.Mock(name="m2", spec=objs.Mount, container_path=cp2)

            volumes = objs.Volumes(mount=[m1, m2], share_with=[])
            assert list(volumes.volume_names) == [cp1, cp2]

    describe "binds":
        it "returns a dictionary from mount pairs":
            key1 = mock.Mock(name="key1")
            key2 = mock.Mock(name="key2")
            val1 = mock.Mock(name="val1")
            val2 = mock.Mock(name="val2")

            m1 = mock.Mock(name="m1", spec=objs.Mount, pair=(key1, val1))
            m2 = mock.Mock(name="m2", spec=objs.Mount, pair=(key2, val2))

            volumes = objs.Volumes(mount=[m1, m2], share_with=[])
            assert volumes.binds == {key1: val1, key2: val2}

describe HarpoonCase, "Mount object":

    @pytest.fixture()
    def M(self):
        class Mocks:
            local_path = self.unique_val()
            container_path = self.unique_val()

        return Mocks

    describe "pair":
        it "returns with ro set to False if permissions are rw", M:
            mount = objs.Mount(M.local_path, M.container_path, "rw")
            assert mount.pair == (M.local_path, {"bind": M.container_path, "ro": False})

        it "returns with ro set to True if permissions are not rw", M:
            mount = objs.Mount(M.local_path, M.container_path, "ro")
            assert mount.pair == (M.local_path, {"bind": M.container_path, "ro": True})

describe HarpoonCase, "Environment":

    @pytest.fixture()
    def env_name(self):
        return self.unique_val()

    @pytest.fixture()
    def fallback_val(self):
        return self.unique_val()

    it "defaults default_val and set_val to None", env_name:
        env = objs.Environment(env_name)
        assert env.default_val is None
        assert env.set_val is None

    describe "pair":

        describe "Env name not in environment":

            @pytest.fixture(autouse=True)
            def assertEnvNotSet(self, env_name):
                assert env_name not in os.environ

            it "returns env_name and default_val if we have a default_val", env_name, fallback_val:
                for val in (fallback_val, ""):
                    env = objs.Environment(env_name, val, None)
                    assert env.pair == (env_name, val)

            it "returns env_name and set_val if we have a set_val", env_name, fallback_val:
                for val in (fallback_val, ""):
                    env = objs.Environment(env_name, None, val)
                    assert env.pair == (env_name, val)

            it "complains if we have no default_val", env_name:
                with assertRaises(KeyError, env_name):
                    env = objs.Environment(env_name)
                    env.pair

        describe "Env name is in environment":

            @pytest.fixture()
            def env_val(self, env_name):
                env_val = self.unique_val()
                original = os.environ.get(env_name, sb.NotSpecified)
                try:
                    os.environ[env_name] = env_val
                    yield env_val
                finally:
                    if original is sb.NotSpecified:
                        if env_name in os.environ:
                            del os.environ[env_name]
                    else:
                        os.environ[env_name] = original

            it "returns the value from the environment if default_val is set", env_name, env_val, fallback_val:
                env = objs.Environment(env_name, fallback_val, None)
                assert env.pair == (env_name, env_val)

            it "returns the set_val if set_val is set", env_name, env_val, fallback_val:
                env = objs.Environment(env_name, None, fallback_val)
                assert env.pair == (env_name, fallback_val)

            it "returns the value from the environment if no default or set val", env_name, env_val:
                env = objs.Environment(env_name)
                assert env.pair == (env_name, env_val)

describe HarpoonCase, "Port object":

    @pytest.fixture()
    def M(self):
        class Mocks:
            ip = self.unique_val()
            host_port = self.unique_val()
            container_port_str = self.unique_val()

        Mocks.container_port = mock.Mock(
            name="container_port", spec=objs.ContainerPort, port_str=Mocks.container_port_str
        )

        return Mocks

    describe "pair":
        it "returns just container_port and host_port if no ip", M:
            port = objs.Port(sb.NotSpecified, M.host_port, M.container_port)
            assert port.pair == (M.container_port_str, M.host_port)

        it "returns container_port with pair of ip and host_port if ip is specified", M:
            port = objs.Port(M.ip, M.host_port, M.container_port)
            assert port.pair == (M.container_port_str, (M.ip, M.host_port))

describe HarpoonCase, "ContainerPort object":

    @pytest.fixture()
    def M(self):
        class Mocks:
            port = self.unique_val()
            transport = self.unique_val()

        return Mocks

    it "defaults transport to sb.NotSpecified", M:
        container_port = objs.ContainerPort(M.port)
        assert container_port.transport == sb.NotSpecified

    describe "Port pair":
        it "defaults transport to tcp", M:
            container_port = objs.ContainerPort(M.port)
            assert container_port.port_pair == (M.port, "tcp")

        it "returns port and transport as a tuple", M:
            container_port = objs.ContainerPort(M.port, M.transport)
            assert container_port.port_pair == (M.port, M.transport)

    describe "Port str":
        it "returns port stringified if no transport":
            port = mock.Mock(name="port")
            container_port = objs.ContainerPort(port)
            assert container_port.port_str == str(port)

        it "returns port and transport as slash joined string", M:
            container_port = objs.ContainerPort(M.port, M.transport)
            assert container_port.port_str == M.port + "/" + M.transport
