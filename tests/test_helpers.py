# coding: spec

import os
from contextlib import contextmanager
from unittest import mock

from harpoon.helpers import a_temp_file, memoized_property, until
from tests.helpers import HarpoonCase

describe HarpoonCase, "a_temp_file":
    it "yields the file object of a file that disappears after the context":
        with a_temp_file() as fle:
            assert os.path.exists(fle.name)
        assert not os.path.exists(fle.name)

    it "can write to the temporary file, close it and still read from it":
        with a_temp_file() as fle:
            fle.write("blah".encode("utf-8"))
            fle.close()
            with open(fle.name) as fread:
                assert fread.read() == "blah"
        assert not os.path.exists(fle.name)

describe HarpoonCase, "until":

    @contextmanager
    def mock_log_and_time(self):
        """Mock out the log object and time, yield (log, time)"""
        fake_log = mock.Mock(name="log")
        fake_time = mock.Mock(name="time")
        with mock.patch("harpoon.helpers.log", fake_log):
            with mock.patch("harpoon.helpers.time", fake_time):
                yield (fake_log, fake_time)

    it "yields before doing anything else":
        done = []
        with self.mock_log_and_time() as (fake_log, fake_time):
            for _ in until():
                done.append(1)
                break

        assert len(fake_time.time.mock_calls) == 0
        assert len(fake_log.info.mock_calls) == 0
        assert done == [1]

    it "logs the action each time":
        done = []
        action = mock.Mock(name="action")
        with self.mock_log_and_time() as (fake_log, fake_time):

            def timer():
                if not done:
                    return 10
                else:
                    return 15

            fake_time.time.side_effect = timer

            for _ in until(action=action):
                if len(done) == 5:
                    break
                else:
                    done.append(1)
        assert done == [1, 1, 1, 1, 1]
        assert fake_log.info.mock_calls == [
            mock.call(action),
            mock.call(action),
            mock.call(action),
            mock.call(action),
            mock.call(action),
        ]

    it "doesn't log the action each time if silent":
        done = []
        action = mock.Mock(name="action")
        with self.mock_log_and_time() as (fake_log, fake_time):
            fake_time.time.return_value = 20
            for _ in until(action=action, silent=True):
                if len(done) == 5:
                    break
                else:
                    done.append(1)
        assert done == [1, 1, 1, 1, 1]
        assert fake_log.info.mock_calls == []

    it "errors out if we have an action and we timeout":
        done = []
        action = mock.Mock(name="action")
        with self.mock_log_and_time() as (fake_log, fake_time):
            info = {"started": False}

            def timer():
                if info["started"]:
                    return 20
                else:
                    info["started"] = True
                    return 1

            fake_time.time.side_effect = timer
            for _ in until(action=action, timeout=2):
                done.append(1)
        assert done == [1]
        assert fake_log.error.mock_calls == [mock.call("Timedout %s", action)]

    it "errors out if we have an action and we timeout unless silent":
        done = []
        action = mock.Mock(name="action")
        with self.mock_log_and_time() as (fake_log, fake_time):
            info = {"started": False}

            def timer():
                if info["started"]:
                    return 20
                else:
                    info["started"] = True
                    return 1

            fake_time.time.side_effect = timer
            for _ in until(action=action, timeout=2, silent=True):
                done.append(1)
        assert done == [1]
        assert fake_log.error.mock_calls == []

    it "sleeps the step each time":
        done = []
        step = mock.Mock(name="step")

        with self.mock_log_and_time() as (fake_log, fake_time):
            fake_time.time.return_value = 20

            def sleeper(self):
                done.append("sleep")

            fake_time.sleep.side_effect = sleeper

            for _ in until(step=step):
                if done.count(1) == 5:
                    done.append("break")
                    break
                else:
                    done.append(1)

        assert done == [1, "sleep", 1, "sleep", 1, "sleep", 1, "sleep", 1, "sleep", "break"]
        assert fake_time.sleep.mock_calls == [
            mock.call(step),
            mock.call(step),
            mock.call(step),
            mock.call(step),
            mock.call(step),
        ]

describe HarpoonCase, "Memoized_property":
    it "takes in a function and sets name and cache_name":

        def a_func_blah():
            pass

        prop = memoized_property(a_func_blah)
        assert prop.func is a_func_blah
        assert prop.name == "a_func_blah"
        assert prop.cache_name == "_a_func_blah"

    it "returns the memoized_property if accessed from the owner":
        owner = type("owner", (object,), {})

        def a_func_blah():
            pass

        prop = memoized_property(a_func_blah)
        assert prop.__get__(None, owner) is prop

        class Things(object):
            @memoized_property
            def blah(self):
                pass

        assert Things.blah.name == "blah"

    it "caches the value on the instance":
        processed = []
        value = mock.Mock(name="value")

        class Things(object):
            @memoized_property
            def yeap(self):
                processed.append(1)
                return value

        instance = Things()

        assert processed == []
        assert not hasattr(instance, "_yeap")

        assert instance.yeap is value
        assert processed == [1]
        assert hasattr(instance, "_yeap")
        assert instance._yeap == value

        # For proof it's not calling yeap again
        assert instance.yeap is value
        assert processed == [1]
        assert hasattr(instance, "_yeap")
        assert instance._yeap == value

        # And proof it's using the _yeap value
        value2 = mock.Mock(name="value2")
        instance._yeap = value2
        assert instance.yeap is value2
        assert processed == [1]
        assert hasattr(instance, "_yeap")
        assert instance._yeap == value2

    it "recomputes the value if the cache isn't there anymore":
        processed = []
        value = mock.Mock(name="value")

        class Things(object):
            @memoized_property
            def yeap(self):
                processed.append(1)
                return value

        instance = Things()

        assert processed == []
        assert not hasattr(instance, "_yeap")

        assert instance.yeap is value
        assert processed == [1]
        assert hasattr(instance, "_yeap")
        assert instance._yeap == value

        # For proof it's not calling yeap again
        assert instance.yeap is value
        assert processed == [1]
        assert hasattr(instance, "_yeap")
        assert instance._yeap == value

        # Unless the value isn't there anymore
        del instance._yeap
        assert instance.yeap is value
        assert processed == [1, 1]
        assert hasattr(instance, "_yeap")
        assert instance._yeap == value

    it "sets the cache value using setattr syntax":
        processed = []
        value = mock.Mock(name="value")

        class Things(object):
            @memoized_property
            def yeap(self):
                processed.append(1)
                return value

        instance = Things()

        assert processed == []
        assert not hasattr(instance, "_yeap")

        instance.yeap = value
        assert instance.yeap is value
        assert processed == []
        assert hasattr(instance, "_yeap")
        assert instance._yeap == value

        value2 = mock.Mock(name="value2")
        instance.yeap = value2
        assert instance.yeap is value2
        assert processed == []
        assert hasattr(instance, "_yeap")
        assert instance._yeap == value2

    it "deletes the cache with del syntax":
        value = mock.Mock(name="value")

        class Things(object):
            @memoized_property
            def yeap(self):
                return value

        instance = Things()

        assert not hasattr(instance, "_yeap")

        instance.yeap = value
        assert instance.yeap is value
        assert hasattr(instance, "_yeap")
        assert instance._yeap == value

        del instance.yeap
        assert not hasattr(instance, "_yeap")
