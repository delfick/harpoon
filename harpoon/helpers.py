from io import TextIOWrapper, StringIO
from contextlib import contextmanager
import tempfile
import logging
import time
import os

log = logging.getLogger("harpoon.helpers")


@contextmanager
def a_temp_file():
    """Yield the name of a temporary file and ensure it's removed after use"""
    filename = None
    try:
        tmpfile = tempfile.NamedTemporaryFile(delete=False)
        filename = tmpfile.name
        yield tmpfile
    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)


def until(timeout=10, step=0.5, action=None, silent=False):
    """Yield until timeout"""
    yield

    started = time.time()
    while True:
        if action and not silent:
            log.info(action)

        if time.time() - started > timeout:
            if action and not silent:
                log.error("Timedout %s", action)
            return
        else:
            time.sleep(step)
            yield


class memoized_property(object):
    """Decorator to make a descriptor that memoizes it's value"""

    def __init__(self, func):
        self.func = func
        self.name = func.__name__
        self.cache_name = "_{0}".format(self.name)

    def __get__(self, instance=None, owner=None):
        if not instance:
            return self

        if not getattr(instance, self.cache_name, None):
            setattr(instance, self.cache_name, self.func(instance))
        return getattr(instance, self.cache_name)

    def __set__(self, instance, value):
        setattr(instance, self.cache_name, value)

    def __delete__(self, instance):
        if hasattr(instance, self.cache_name):
            delattr(instance, self.cache_name)


def write_to(output, txt):
    """Write some text to some output"""
    if isinstance(txt, bytes) and isinstance(output, StringIO):
        output.write(txt.decode("utf-8", "replace"))
    elif (
        isinstance(txt, str)
        and hasattr(output, "file")
        and "b" in getattr(output.file, "mode", "w")
    ):
        output.write(txt.encode("utf-8", "replae"))
    else:
        output.write(txt)
