import os
import sys
import tempfile

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    if "DESTRUCTIVE_DOCKER_TESTS" not in os.environ:
        pytest.skip("Not doing destructive docker tests")


@pytest.fixture(autouse=True)
def replace_stdin():
    current = sys.stdin
    fle = None
    try:
        fle = tempfile.NamedTemporaryFile(delete=False)
        sys.stdin = fle
        yield
    finally:
        sys.stdin = current
        if fle and os.path.exists(fle.name):
            os.remove(fle.name)
