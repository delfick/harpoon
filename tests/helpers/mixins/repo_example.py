from harpoon.processes import command_output
from harpoon.errors import HarpoonError

from contextlib import contextmanager
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
            output, status = command_output("git clone", os.path.join(this_dir, '..', 'repo_example', 'example.bundle'), directory)
            if status != 0:
                raise HarpoonError("Failed to run git clone", output='\n'.join(output))

            # For shallow clones, have to clone twice, seems --depth with bundles don't work
            if shallow:
                with self.a_temp_dir() as directory2:
                    shutil.rmtree(directory2)
                    output, status = command_output("git clone --depth 1", "file://{0}".format(directory), directory2)
                    if status != 0:
                        raise HarpoonError("Failed to run git clone", output='\n'.join(output))
                    yield directory2
            else:
                yield directory

