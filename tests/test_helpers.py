# coding: spec

from harpoon.helpers import a_temp_file, until, memoized_property

from tests.helpers import HarpoonCase

from noseOfYeti.tokeniser.support import noy_sup_setUp
from contextlib import contextmanager
import mock
import os

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
                self.assertEqual(fread.read(), "blah")
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

        self.assertEqual(len(fake_time.time.mock_calls), 0)
        self.assertEqual(len(fake_log.info.mock_calls), 0)
        self.assertEqual(done, [1])

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
        self.assertEqual(done, [1, 1, 1, 1, 1])
        self.assertEqual(fake_log.info.mock_calls, [mock.call(action), mock.call(action), mock.call(action), mock.call(action), mock.call(action)])

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
        self.assertEqual(done, [1, 1, 1, 1, 1])
        self.assertEqual(fake_log.info.mock_calls, [])

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
        self.assertEqual(done, [1])
        self.assertEqual(fake_log.error.mock_calls, [mock.call("Timedout %s", action)])

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
        self.assertEqual(done, [1])
        self.assertEqual(fake_log.error.mock_calls, [])

    it "sleeps the step each time":
        done = []
        step = mock.Mock(name="step")
        action = mock.Mock(name="action")

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

        self.assertEqual(done, [1, "sleep", 1, "sleep", 1, "sleep", 1, "sleep", 1, "sleep", "break"])
        self.assertEqual(fake_time.sleep.mock_calls, [mock.call(step), mock.call(step), mock.call(step), mock.call(step), mock.call(step)])

