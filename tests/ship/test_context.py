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
        self.mtime = int(time.time())
        self.docker_lines = '\n'.join(["FROM somewhere", "RUN touch /tmp/stuff"])
        self.docker_file = objs.DockerFile(self.docker_lines, self.mtime)
        self.context = objs.Context(enabled=True, parent_dir=self.folder)

    describe "make_context":
        it "adds Dockerfile and everything from find_mtimes":
            find_mtimes = mock.Mock(name="find_mtimes")
            one_val = self.unique_val()
            two_val = self.unique_val()
            mtime = int(time.time())
            folder, files = self.setup_directory({"one": {"1": one_val}, "two": two_val}, root=self.folder)
            find_mtimes.return_value = [(files["one"]["/folder/"], mtime, './one'), (files["one"]["1"]["/file/"], mtime, "./one/1"), (files["two"]["/file/"], mtime, "./two")]

            with mock.patch.object(ContextBuilder, "find_mtimes", find_mtimes):
                with ContextBuilder().make_context(self.context, self.docker_file) as tmpfile:
                    self.assertTarFileContent(tmpfile.name
                        , {"./one": (mtime, None), "./one/1": (mtime, one_val), "./two": (mtime, two_val), "./Dockerfile": (self.mtime, self.docker_lines)}
                        )

        it "adds extra_content after find_mtimes":
            find_mtimes = mock.Mock(name="find_mtimes")
            one_val = self.unique_val()
            two_val = self.unique_val()

            three_val = self.unique_val()
            four_val = self.unique_val()
            extra_context = [(three_val, "./one"), (four_val, "./four")]

            mtime = int(time.time())
            folder, files = self.setup_directory({"one": one_val, "two": two_val}, root=self.folder)
            find_mtimes.return_value = [(files["one"]["/file/"], mtime, './one'), (files["two"]["/file/"], mtime, "./two")]

            with mock.patch.object(ContextBuilder, "find_mtimes", find_mtimes):
                with ContextBuilder().make_context(self.context, self.docker_file, extra_context=extra_context) as tmpfile:
                    self.assertTarFileContent(tmpfile.name
                        , {"./one": (mtime, three_val), "./two": (mtime, two_val), "./four": (self.mtime, four_val), "./Dockerfile": (self.mtime, self.docker_lines)}
                        )

