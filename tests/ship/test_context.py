# coding: spec

from harpoon.option_spec import image_objs as objs
from harpoon.ship.context import ContextBuilder

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
import time
import mock

describe HarpoonCase, "Context builder":
    before_each:
        self.folder = self.make_temp_dir()
        self.context = objs.Context(enabled=True, parent_dir=self.folder)

        self.one_val = self.unique_val()
        self.one_mtime = int(time.time())

        self.two_val = self.unique_val()
        self.two_mtime = int(time.time()) + 10

        self.three_val = self.unique_val()
        self.three_mtime = int(time.time()) + 11

        self.four_val = self.unique_val()
        self.four_mtime = int(time.time()) + 20

    describe "make_context":
        before_each:
            self.mtime = int(time.time())
            self.docker_lines = '\n'.join(["FROM somewhere", "RUN touch /tmp/stuff"])
            self.docker_file = objs.DockerFile(self.docker_lines, self.mtime)

        it "adds Dockerfile and everything from find_mtimes":
            find_mtimes = mock.Mock(name="find_mtimes")
            mtime = int(time.time())
            folder, files = self.setup_directory({"one": {"1": self.one_val}, "two": self.two_val}, root=self.folder)
            find_mtimes.return_value = [(files["one"]["/folder/"], mtime, './one'), (files["one"]["1"]["/file/"], mtime, "./one/1"), (files["two"]["/file/"], mtime, "./two")]

            with mock.patch.object(ContextBuilder, "find_mtimes", find_mtimes):
                with ContextBuilder().make_context(self.context, self.docker_file) as tmpfile:
                    self.assertTarFileContent(tmpfile.name
                        , {"./one": (mtime, None), "./one/1": (mtime, self.one_val), "./two": (mtime, self.two_val), "./Dockerfile": (self.mtime, self.docker_lines)}
                        )

        it "adds extra_content after find_mtimes":
            find_mtimes = mock.Mock(name="find_mtimes")
            extra_context = [(self.three_val, "./one"), (self.four_val, "./four")]

            mtime = int(time.time())
            folder, files = self.setup_directory({"one": self.one_val, "two": self.two_val}, root=self.folder)
            find_mtimes.return_value = [(files["one"]["/file/"], mtime, './one'), (files["two"]["/file/"], mtime, "./two")]

            with mock.patch.object(ContextBuilder, "find_mtimes", find_mtimes):
                with ContextBuilder().make_context(self.context, self.docker_file, extra_context=extra_context) as tmpfile:
                    self.assertTarFileContent(tmpfile.name
                        , {"./one": (mtime, self.three_val), "./two": (mtime, self.two_val), "./four": (self.mtime, self.four_val), "./Dockerfile": (self.mtime, self.docker_lines)}
                        )

