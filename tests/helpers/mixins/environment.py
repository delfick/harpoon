import os
from contextlib import contextmanager


class EnvironmentAssertionsMixin:
    @contextmanager
    def modified_env(self, **env):
        originals = dict(os.environ)
        try:
            for key, val in env.items():
                os.environ[key] = val
            yield
        finally:
            if type(env) is dict:
                for key in env:
                    if key in originals:
                        os.environ[key] = originals[key]
                    elif key in os.environ:
                        del os.environ[key]
