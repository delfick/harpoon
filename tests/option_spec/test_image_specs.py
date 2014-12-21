# coding: spec

from harpoon.option_spec import image_specs as specs, image_objs as objs

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
from input_algorithms.spec_base import NotSpecified
from input_algorithms.dictobj import dictobj
from input_algorithms.meta import Meta
from option_merge import MergedOptions
import mock

describe HarpoonCase, "Command spec":
    before_each:
        self.meta = mock.Mock(name="meta", spec=Meta)

    it "returns a command object":
        command = mock.Mock(name="command")
        command_object = specs.command_spec().normalise(self.meta, command)
        self.assertIs(command_object.meta, self.meta)
        self.assertIs(command_object.orig_command, command)

describe HarpoonCase, "Mount spec":
    before_each:
        self.meta = mock.Mock(name="meta", spec=Meta)
        self.local_path = self.unique_val()
        self.container_path = self.unique_val()

    def do_check(self, value, permissions):
        made = specs.mount_spec().normalise(self.meta, value)
        self.assertEqual(made.local_path, self.local_path)
        self.assertEqual(made.container_path, self.container_path)
        self.assertEqual(made.permissions, permissions)

    it "takes as [local_path, container_path]":
        self.do_check([self.local_path, self.container_path], "rw")

    it "takes as [local_path, container_path, permissions]":
        self.do_check([self.local_path, self.container_path, "ro"], "ro")

    it "takes as local_path:container_path":
        self.do_check("{0}:{1}".format(self.local_path, self.container_path), "rw")

    it "takes as local_path:container_path:permissions":
        self.do_check("{0}:{1}:ro".format(self.local_path, self.container_path, "ro"), "ro")

describe HarpoonCase, "Env spec":
    before_each:
        self.meta = mock.Mock(name="meta", spec=Meta)
        self.set_val = self.unique_val()
        self.env_name = self.unique_val()
        self.default_val = self.unique_val()

    def do_check(self, value, has_default, has_set, empty_default=False, empty_set=False):
        made = specs.env_spec().normalise(self.meta, value)
        self.assertEqual(made.env_name, self.env_name)

        if has_default:
            self.assertEqual(made.default_val, "" if empty_default else self.default_val)
        else:
            self.assertIs(made.default_val, None)

        if has_set:
            self.assertEqual(made.set_val, "" if empty_set else self.set_val)
        else:
            self.assertIs(made.set_val, None)

    it "takes in env as a list with 1 to 2 items":
        self.do_check([self.env_name], has_default=False, has_set=False)
        self.do_check([self.env_name, self.default_val], has_default=True, has_set=False)

    it "takes in env with blank default if suffixed with a colon":
        self.do_check("{0}:".format(self.env_name), has_default=True, has_set=False, empty_default=True)

    it "takes in env with blank set if suffixed with an equals sign":
        self.do_check("{0}=".format(self.env_name), has_default=False, has_set=True, empty_set=True)

    it "takes in default value if seperated by a colon":
        self.do_check("{0}:{1}".format(self.env_name, self.default_val), has_default=True, has_set=False)

    it "takes in set value if seperated by an equals sign":
        self.do_check("{0}={1}".format(self.env_name, self.set_val), has_default=False, has_set=True)

describe HarpoonCase, "Link spec":
    before_each:

        class container(dictobj):
            fields = ['container_name']

        self.meta = mock.Mock(name="meta", spec=Meta)
        self.container_alias = self.unique_val()
        self.container = container("somewhere.com/{0}".format(self.container_alias))
        self.converted_container_name = "somewhere.com-{0}".format(self.container_alias)
        self.meta.everything = MergedOptions.using({"container": self.container}, dont_prefix=[dictobj])

    def do_check(self, value, container, expected_alias):
        made = specs.link_spec().normalise(self.meta, value)
        self.assertEqual(made.container, container)
        self.assertEqual(made.container_name, self.container.container_name)
        self.assertEqual(made.link_name, expected_alias)

    it "takes in as a list of 1 or two items":
        self.do_check(["{container}"], container=self.container, expected_alias=self.converted_container_name)
        self.do_check(["{container}", self.container_alias], container=self.container, expected_alias=self.container_alias)

    it "takes in as a colon seperated list":
        self.do_check("{{container}}:{0}".format(self.container_alias), container=self.container, expected_alias=self.container_alias)

    it "doesn't need a container":
        self.do_check("{0}:{1}".format(self.container.container_name, self.container_alias), container=None, expected_alias=self.container_alias)
        self.do_check([self.container.container_name, self.container_alias], container=None, expected_alias=self.container_alias)

describe HarpoonCase, "Port spec":
    before_each:
        self.meta = mock.Mock(name="meta", spec=Meta)
        self.ip = self.unique_val()
        self.host_port = 80
        self.container_port = 70
        self.container_port_val = lambda transport: objs.ContainerPort(70, transport)

    def do_check(self, value, has_ip, has_host_port, has_container_port, expected_transport=NotSpecified):
        made = specs.port_spec().normalise(self.meta, value)

        if has_ip:
            self.assertEqual(made.ip, self.ip)
        else:
            self.assertEqual(made.ip, NotSpecified)

        if has_host_port:
            self.assertEqual(made.host_port, self.host_port)
        else:
            self.assertEqual(made.host_port, NotSpecified)

        if has_container_port:
            self.assertEqual(made.container_port, self.container_port_val(expected_transport))
        else:
            self.assertEqual(made.container_port, NotSpecified)

    it "takes as a list of 1 to 3 items":
        self.do_check([self.container_port], has_ip=False, has_host_port=False, has_container_port=True)
        self.do_check(["{0}/tcp".format(self.container_port)], has_ip=False, has_host_port=False, has_container_port=True, expected_transport="tcp")

        self.do_check([self.host_port, self.container_port], has_ip=False, has_host_port=True, has_container_port=True)
        self.do_check([self.ip, self.host_port, self.container_port], has_ip=True, has_host_port=True, has_container_port=True)

    it "takes as a colon seperated list of 1 to 3 items":
        self.do_check("{0}".format(self.container_port), has_ip=False, has_host_port=False, has_container_port=True)
        self.do_check("{0}/tcp".format(self.container_port), has_ip=False, has_host_port=False, has_container_port=True, expected_transport="tcp")

        self.do_check("{0}:{1}".format(self.host_port, self.container_port), has_ip=False, has_host_port=True, has_container_port=True)

        self.do_check("{0}:{1}:{2}".format(self.ip, self.host_port, self.container_port), has_ip=True, has_host_port=True, has_container_port=True)
        self.do_check("{0}::{1}".format(self.ip, self.container_port), has_ip=True, has_host_port=False, has_container_port=True)
        self.do_check("{0}::{1}/tcp".format(self.ip, self.container_port), has_ip=True, has_host_port=False, has_container_port=True, expected_transport="tcp")

describe HarpoonCase, "Container Port Spec":
    before_each:
        self.meta = mock.Mock(name="meta", spec=Meta)

    it "defaults transport to NotSpecified":
        self.assertEqual(specs.container_port_spec().normalise(self.meta, "80"), objs.ContainerPort(80, NotSpecified))

    it "takes in transport as a string or as a list":
        self.assertEqual(specs.container_port_spec().normalise(self.meta, "80/tcp"), objs.ContainerPort(80, "tcp"))
        self.assertEqual(specs.container_port_spec().normalise(self.meta, ["80", "tcp"]), objs.ContainerPort(80, "tcp"))

