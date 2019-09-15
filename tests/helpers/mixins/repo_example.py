from contextlib import contextmanager
from textwrap import dedent
import subprocess
import shutil
import os

this_dir = os.path.dirname(__file__)


class Repo_exampleAssertionsMixin:
    def repo_example_map(self):
        location = os.path.join(this_dir, "..", "repo_example", "map")
        with open(location) as fle:
            lines = list(fle.readlines())

        result = {}
        for line in lines:
            date, filename = line.split(" ", 1)
            result[filename.strip()] = int(date)

        return result

    @contextmanager
    def cloned_repo_example(self, shallow=False):
        with self.a_temp_dir() as directory:
            shutil.rmtree(directory)
            bundle = os.path.join(this_dir, "..", "repo_example", "example.bundle")
            kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "check": True}
            subprocess.run(["git", "clone", bundle, directory], **kwargs)

            # For shallow clones, have to clone twice, seems --depth with bundles don't work
            if shallow:
                with self.a_temp_dir() as directory2:
                    shutil.rmtree(directory2)
                    d = "file://{0}".format(directory)
                    subprocess.run(["git", "clone", "--depth", "1", d, directory2], **kwargs)
                    yield directory2
            else:
                yield directory

    def assertExampleRepoStatus(self, root_folder, expected, sort_output=False):
        output = subprocess.check_output(["git", "status", "-s"], cwd=root_folder)
        lines = output.decode().strip().split("\n")
        expected = dedent(expected).strip().split("\n")

        if sort_output:
            lines = sorted(lines)
            expected = sorted(expected)

        self.assertEqual("\n".join(lines), "\n".join(expected))
