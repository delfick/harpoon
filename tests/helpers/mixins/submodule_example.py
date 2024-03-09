import os
import shutil
import subprocess
from contextlib import contextmanager

this_dir = os.path.dirname(__file__)


class Submodule_exampleAssertionsMixin:
    @contextmanager
    def cloned_submodule_example(self):
        with self.a_temp_dir() as directory:
            shutil.rmtree(directory)
            os.makedirs(directory)

            two_bundle = os.path.join(this_dir, "..", "submodule_example", "two.bundle")
            two_dir = os.path.join(directory, "two")

            one_bundle = os.path.join(this_dir, "..", "submodule_example", "one.bundle")
            one_dir = os.path.join(directory, "one")

            kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "check": True}

            subprocess.run(["git", "clone", two_bundle, two_dir], **kwargs)
            subprocess.run(["git", "clone", one_bundle, one_dir], **kwargs)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "protocol.file.allow=always",
                    "submodule",
                    "add",
                    two_dir,
                    "vendor/two",
                ],
                cwd=one_dir,
                **kwargs,
            )

            yield one_dir
