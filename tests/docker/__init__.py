import nose
import os

if os.environ.get("DESTRUCTIVE_DOCKER_TESTS") is None:
    raise nose.SkipTest()
