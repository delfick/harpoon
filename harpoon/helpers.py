from contextlib import contextmanager
import tempfile
import logging
import time
import os

log = logging.getLogger("harpoon.helpers")

@contextmanager
def a_temp_file():
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

