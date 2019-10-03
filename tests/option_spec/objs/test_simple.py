# coding: spec

from harpoon.option_spec import image_objs as objs
from harpoon.errors import HarpoonError

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp, noy_sup_tearDown
from delfick_project.norms import sb
import mock
import os

describe HarpoonCase, "Context object":
    before_each:
        self.include = [self.unique_val()]
        self.exclude = [self.unique_val()]
        self.enabled = mock.Mock(name="enabled")
        self.parent_dir = self.unique_val()

    it "defaults _use_gitignore and to sb.NotSpecified an include and exclude to None":
        ctxt = objs.Context(enabled=self.enabled, parent_dir=self.parent_dir)
        assert ctxt.enabled is self.enabled
        assert ctxt.parent_dir == os.path.abspath(self.parent_dir)
        assert ctxt.include is None
        assert ctxt.exclude is None
        assert ctxt._use_gitignore is sb.NotSpecified

    describe "use_gitignore":
        it "returns False if _use_gitignore is sb.NotSpecified":
            ctxt = objs.Context(enabled=True, parent_dir=self.parent_dir)
            assert ctxt.use_gitignore is False

        it "returns the value of _use_gitignore otherwise":
            ctxt = objs.Context(enabled=True, parent_dir=self.parent_dir)
            ugi = mock.Mock(name="use_gitignore")
            ctxt.use_gitignore = ugi
            assert ctxt.use_gitignore is ugi

            ctxt = objs.Context(use_gitignore=ugi, enabled=True, parent_dir=self.parent_dir)
            assert ctxt.use_gitignore is ugi

    describe "parent_dir":
        it "gets set as the abspath of the value":
            parent_dir = mock.Mock(name="parent_dir")
            abs_parent_dir = mock.Mock(name="abs_parent_dir")
            with mock.patch("os.path.abspath") as fake_abspath:
                fake_abspath.return_value = abs_parent_dir
                assert (
                    objs.Context(enabled=self.enabled, parent_dir=parent_dir).parent_dir
                    is abs_parent_dir
                )
                fake_abspath.assert_called_once_with(parent_dir)

    describe "git_root":
        it "goes up directories till it finds the .git folder":
            with self.a_temp_dir() as directory:
                parent_dir = os.path.join(directory, "blah", ".git", "meh", "stuff")
                os.makedirs(parent_dir)
                assert objs.Context(
                    enabled=self.enabled, parent_dir=parent_dir
                ).git_root == os.path.abspath(os.path.join(directory, "blah"))

        it "complains if it can't find a .git folder":
            with self.a_temp_dir() as directory:
                nxt = directory
                while nxt != "/" and not os.path.exists(os.path.join(nxt, ".git")):
                    nxt = os.path.dirname(nxt)
                assert not os.path.exists(os.path.join(nxt, ".git"))

                with self.fuzzyAssertRaisesError(
                    HarpoonError, "Couldn't find a .git folder", start_at=directory
                ):
                    objs.Context(enabled=self.enabled, parent_dir=directory).git_root

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
    before_each:
        self.local_path = self.unique_val()
        self.container_path = self.unique_val()

    describe "pair":
        it "returns with ro set to False if permissions are rw":
            mount = objs.Mount(self.local_path, self.container_path, "rw")
            assert mount.pair == (self.local_path, {"bind": self.container_path, "ro": False})

        it "returns with ro set to True if permissions are not rw":
            mount = objs.Mount(self.local_path, self.container_path, "ro")
            assert mount.pair == (self.local_path, {"bind": self.container_path, "ro": True})

describe HarpoonCase, "Environment":
    before_each:
        self.env_name = self.unique_val()
        self.fallback_val = self.unique_val()

    it "defaults default_val and set_val to None":
        env = objs.Environment(self.env_name)
        assert env.default_val is None
        assert env.set_val is None

    describe "pair":

        describe "Env name not in environment":
            before_each:
                assert self.env_name not in os.environ

            it "returns env_name and default_val if we have a default_val":
                for val in (self.fallback_val, ""):
                    env = objs.Environment(self.env_name, val, None)
                    assert env.pair == (self.env_name, val)

            it "returns env_name and set_val if we have a set_val":
                for val in (self.fallback_val, ""):
                    env = objs.Environment(self.env_name, None, val)
                    assert env.pair == (self.env_name, val)

            it "complains if we have no default_val":
                with self.fuzzyAssertRaisesError(KeyError, self.env_name):
                    env = objs.Environment(self.env_name)
                    env.pair

        describe "Env name is in environment":
            before_each:
                self.env_val = self.unique_val()
                os.environ[self.env_name] = self.env_val

            after_each:
                del os.environ[self.env_name]

            it "returns the value from the environment if default_val is set":
                env = objs.Environment(self.env_name, self.fallback_val, None)
                assert env.pair == (self.env_name, self.env_val)

            it "returns the set_val if set_val is set":
                env = objs.Environment(self.env_name, None, self.fallback_val)
                assert env.pair == (self.env_name, self.fallback_val)

            it "returns the value from the environment if no default or set val":
                env = objs.Environment(self.env_name)
                assert env.pair == (self.env_name, self.env_val)

describe HarpoonCase, "Port object":
    before_each:
        self.ip = self.unique_val()
        self.host_port = self.unique_val()
        self.container_port_str = self.unique_val()
        self.container_port = mock.Mock(
            name="container_port", spec=objs.ContainerPort, port_str=self.container_port_str
        )

    describe "pair":
        it "returns just container_port and host_port if no ip":
            port = objs.Port(sb.NotSpecified, self.host_port, self.container_port)
            assert port.pair == (self.container_port_str, self.host_port)

        it "returns container_port with pair of ip and host_port if ip is specified":
            port = objs.Port(self.ip, self.host_port, self.container_port)
            assert port.pair == (self.container_port_str, (self.ip, self.host_port))

describe HarpoonCase, "ContainerPort object":
    before_each:
        self.port = self.unique_val()
        self.transport = self.unique_val()

    it "defaults transport to sb.NotSpecified":
        container_port = objs.ContainerPort(self.port)
        assert container_port.transport == sb.NotSpecified

    describe "Port pair":
        it "defaults transport to tcp":
            container_port = objs.ContainerPort(self.port)
            assert container_port.port_pair == (self.port, "tcp")

        it "returns port and transport as a tuple":
            container_port = objs.ContainerPort(self.port, self.transport)
            assert container_port.port_pair == (self.port, self.transport)

    describe "Port str":
        it "returns port stringified if no transport":
            port = mock.Mock(name="port")
            container_port = objs.ContainerPort(port)
            assert container_port.port_str == str(port)

        it "returns port and transport as slash joined string":
            container_port = objs.ContainerPort(self.port, self.transport)
            assert container_port.port_str == self.port + "/" + self.transport
