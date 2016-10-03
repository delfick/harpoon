from harpoon.errors import HarpoonError

from delfick_app import command_output
from contextlib import contextmanager
from textwrap import dedent
import shutil
import os

this_dir = os.path.dirname(__file__)

class Submodule_exampleAssertionsMixin:
    @contextmanager
    def cloned_submodule_example(self):
        with self.a_temp_dir() as directory:
            shutil.rmtree(directory)
            os.makedirs(directory)

            output, status = command_output("git clone", os.path.join(this_dir, '..', 'submodule_example', 'two.bundle'), os.path.join(directory, "two"))
            if status != 0:
                raise HarpoonError("Failed to run git clone", output='\n'.join(output))

            output, status = command_output("git clone", os.path.join(this_dir, '..', 'submodule_example', 'one.bundle'), os.path.join(directory, "one"))
            if status != 0:
                raise HarpoonError("Failed to run git clone", output='\n'.join(output))

            output, status = command_output("bash -c 'cd {0}/one && git submodule add {0}/two vendor/two'".format(directory))
            if status != 0:
                raise HarpoonError("Failed to run git submodule add", output='\n'.join(output))

            yield os.path.join(directory, "one")

