# coding: spec

from tests.option_spec.specs.test_command_specs import CommandCase

from harpoon.option_spec.image_objs import Image, Context
from harpoon.errors import BadSpecValue, ProgrammerError
from harpoon.option_spec import command_specs as cs
from harpoon.option_spec import command_objs as co

from noseOfYeti.tokeniser.support import noy_sup_setUp
from input_algorithms.spec_base import NotSpecified
from input_algorithms.meta import Meta
import hashlib
import json
import mock

describe CommandCase, "Complex ADD spec":
    before_each:
        self.spec = cs.complex_ADD_spec()

    it "complains if we have conflicting options":
        val1 = {"content": self.unique_val(), "context": self.unique_val()}
        val2 = {"get": self.unique_val(), "prefix": self.unique_val(), "content": self.unique_val()}
        val3 = {"get": self.unique_val(), "prefix": self.unique_val(), "context": self.unique_val()}
        val4 = {}
        for val in (val1, val2, val3, val4):
            with self.fuzzyAssertRaisesError(BadSpecValue):
                self.spec.normalise(self.meta, val)

    it "complains if dest does not accompany content":
        command = {"content": "blah"}
        with self.fuzzyAssertRaisesError(
            BadSpecValue,
            _errors=[BadSpecValue("Expected a value but got none", meta=self.meta.at("dest"))],
        ):
            self.spec.normalise(self.meta, command)

    it "complains if dest does not accompany context":
        command = {"context": {"parent_dir": "."}}
        with self.fuzzyAssertRaisesError(
            BadSpecValue,
            _errors=[BadSpecValue("Expected a value but got none", meta=self.meta.at("dest"))],
        ):
            self.spec.normalise(self.meta, command)

    it "complains if get is not a string or list":
        for get in (0, 1, None, True, False, {}, {1: 2}, type("adf", (object,), {})(), lambda: 1):
            command = {"get": get}
            actual_error = BadSpecValue(
                "Expected a string", got=type(get), meta=self.meta.at("get").indexed_at(0)
            )
            with self.fuzzyAssertRaisesError(
                BadSpecValue,
                _errors=[BadSpecValue(meta=self.meta.at("get"), _errors=[actual_error])],
            ):
                self.spec.normalise(self.meta, command)

    describe "With get":
        it "takes the tedium out of adding multiple files to a destination with the same name":
            command = {"get": ["one", "two", "three"]}
            self.assertDockerLines(command, ["ADD one one", "ADD two two", "ADD three three"])

        it "takes a prefix to add to all the files":
            command = {"get": ["one", "two", "three"], "prefix": "/project"}
            self.assertDockerLines(
                command,
                ["ADD one /project/one", "ADD two /project/two", "ADD three /project/three"],
            )

    describe "with context":
        it "adds a context.tar to the container":
            parent_dir = self.make_temp_dir()

            md5 = self.unique_val()
            dest = "/somewhere/nice and fun"
            command = {"context": {"parent_dir": parent_dir}, "dest": dest}

            with mock.patch(
                "harpoon.option_spec.command_specs.CommandContent.make_hash", lambda *args: md5
            ):
                result = self.spec.normalise(self.meta, command)

            self.assertEqual(len(result), 1)
            result = result[0]
            self.assertEqual(result.action, "ADD")
            self.assertEqual(
                result.extra_context[1], "{0}--somewhere-nice--and--fun.tar".format(md5)
            )

            ctxt = result.extra_context[0]["context"]
            self.assertEqual(type(ctxt), Context)
            self.assertEqual(ctxt.parent_dir, parent_dir)

    describe "With string content":
        it "sets extra context using the content and dest":
            dest = "/somewhere/nice and fun"
            content = "blah de blah blah da"
            command = {"content": content, "dest": dest}

            result = self.spec.normalise(self.meta, command)
            self.assertEqual(len(result), 1)
            result = result[0]
            self.assertEqual(result.action, "ADD")
            md5 = hashlib.md5(json.dumps({"content": content}).encode("utf-8")).hexdigest()
            self.assertEqual(
                result.extra_context, (content, "{0}--somewhere-nice--and--fun".format(md5))
            )

        it "sets command as adding in context dest to actual dest":
            dest = "/somewhere/nice and fun"
            content = "blah de blah blah da"
            command = {"content": content, "dest": dest}
            result = self.spec.normalise(self.meta, command)
            self.assertEqual(len(result), 1)
            result = result[0]
            self.assertDockerLines(command, ["ADD {0} {1}".format(result.extra_context[1], dest)])

    describe "with dict content":
        it "sets extra context using the image and path":
            dest = "/somewhere/nice and fun"
            command = {"content": {"image": "blah2", "path": "/somewhere/better"}, "dest": dest}

            md5 = self.unique_val()
            images = mock.Mock(name="images")
            self.meta.everything["images"] = images

            with mock.patch(
                "harpoon.option_spec.command_specs.CommandContent.make_hash", lambda *args: md5
            ):
                result = self.spec.normalise(self.meta, command)

            self.assertEqual(len(result), 1)
            result = result[0]
            self.assertEqual(result.action, "ADD")
            self.assertEqual(result.extra_context[1], "{0}--somewhere-nice--and--fun".format(md5))

            options = result.extra_context[0]
            self.assertIs(options.images, images)
            self.assertIs(options.docker_api, self.harpoon.docker_api)
            self.assertIs(type(options.conf), Image)
            self.assertEqual(options.conf.image_name, "blah2")
            self.assertEqual(options.path, "/somewhere/better")

describe CommandCase, "CommandContentAddString":
    it "resolves to the content":
        content = mock.Mock(name="content")
        self.assertIs(cs.CommandContentAddString(content).resolve(), content)

    it "returns content for_json":
        content = mock.Mock(name="content")
        self.assertIs(cs.CommandContentAddString(content).for_json(), content)

describe CommandCase, "CommandContent":
    it "cannot be instantiated by itself":
        with self.fuzzyAssertRaisesError(ProgrammerError):
            cs.CommandContent()

    it "has a context_name functionality":
        md5 = self.unique_val()

        class Subclass(cs.CommandContent):
            fields = ["dest"]

            def make_hash(self):
                return md5

        meta = Meta({}, [])
        sc = Subclass("somewhere/nice")
        self.assertEqual(sc.context_name(meta), "{0}-somewhere-nice".format(md5))

    it "makes a hash with a json dump sorting keys":

        class Subclass(cs.CommandContent):
            def for_json(self):
                return {"one": 1, "two": 2}

        sc = Subclass()
        self.assertEqual(
            sc.make_hash(),
            hashlib.md5(
                json.dumps({"content": {"one": 1, "two": 2}}, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        )

describe CommandCase, "CommandContextAdd":
    describe "for_json":
        it "returns context as a dict as a string":
            asd = self.unique_val()
            ctxt = mock.Mock(name="ctxt", as_dict=lambda: asd)
            obj = cs.CommandContextAdd(dest="/somewhere", context=ctxt)
            self.assertEqual(obj.for_json(), asd)

    describe "commands":
        it "yields one command with the tar file and context as extra_context":
            meta = mock.Mock(name="meta")
            ctxt = mock.Mock(name="context")
            context_name = self.unique_val()

            with mock.patch(
                "harpoon.option_spec.command_specs.CommandContent.context_name",
                lambda *args: context_name,
            ):
                obj = cs.CommandContextAdd(dest="/somwehere", context=ctxt)
                commands = list(obj.commands(meta))
                self.assertEqual(len(commands), 1)
                self.assertEqual(
                    commands[0].instruction, ("ADD", "{0}.tar /somwehere".format(context_name))
                )
                self.assertEqual(commands[0].extra_context[1], "{0}.tar".format(context_name))
                self.assertEqual(commands[0].extra_context[0], {"context": ctxt})

describe CommandCase, "CommandContentAdd":
    describe "for_json":
        it "returns context as content.for_json":
            asd = self.unique_val()
            content = mock.Mock(name="ctxt", for_json=lambda: asd)
            obj = cs.CommandContentAdd(dest="/somewhere", content=content)
            self.assertEqual(obj.for_json(), asd)

    describe "commands":
        it "yields one command with the content.resolve and context_name as extra_context":
            meta = mock.Mock(name="meta")
            content = mock.Mock(name="content")

            resolved = self.unique_val()
            context_name = self.unique_val()
            content.resolve.return_value = resolved

            with mock.patch(
                "harpoon.option_spec.command_specs.CommandContent.context_name",
                lambda *args: context_name,
            ):
                obj = cs.CommandContentAdd(dest="/somwehere", content=content)
                commands = list(obj.commands(meta))
                self.assertEqual(len(commands), 1)
                self.assertEqual(
                    commands[0].instruction, ("ADD", "{0} /somwehere".format(context_name))
                )
                self.assertEqual(commands[0].extra_context[1], "{0}".format(context_name))
                self.assertEqual(commands[0].extra_context[0], resolved)

describe CommandCase, "CommandContentAddDict":
    before_each:
        self.image = mock.Mock(name="image")
        self.conf = mock.Mock(name="conf")
        self.path = mock.Mock(name="path")
        self.images = mock.Mock(name="images")

    it "resolves to itself":
        obj = cs.CommandContentAddDict(
            image=self.image,
            conf=self.conf,
            path=self.path,
            images=self.images,
            docker_api=self.docker_api,
        )
        self.assertIs(obj.resolve(), obj)

    it "just uses image_name and path in for_json":
        obj = cs.CommandContentAddDict(
            image=self.image,
            conf=self.conf,
            path=self.path,
            images=self.images,
            docker_api=self.docker_api,
        )
        image_name = self.unique_val()
        self.conf.image_name = image_name
        self.assertEqual(obj.for_json(), {"image": image_name, "path": self.path})

describe CommandCase, "CommandAddExtra":
    it "yields commands for each value in get":
        meta = mock.Mock(name="meta")
        v1, r1 = mock.Mock(name="v1"), mock.Mock(name="r1")
        v2, r2 = mock.Mock(name="v2"), mock.Mock(name="r2")
        v3, r3 = mock.Mock(name="v3"), mock.Mock(name="r3")
        transform = {v1: r1, v2: r2, v3: r3}

        command_for = mock.Mock(name="command_for")
        command_for.side_effect = lambda v: transform[v]

        obj = cs.CommandAddExtra(get=[v1, v2, v3], prefix=NotSpecified)
        c = lambda r: co.Command(("ADD", r))

        with mock.patch.object(obj, "command_for", command_for):
            self.assertEqual(list(obj.commands(meta)), [c(r1), c(r2), c(r3)])

    it "yields command without prefix if no prefix is specified":
        obj = cs.CommandAddExtra(get=[], prefix=NotSpecified)
        self.assertEqual(obj.command_for("blah"), "blah blah")

    it "yields command with prefix if prefix is specified":
        obj = cs.CommandAddExtra(get=[], prefix="/stuff")
        self.assertEqual(obj.command_for("blah"), "blah /stuff/blah")
