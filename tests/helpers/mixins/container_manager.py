from harpoon.container_manager import make_server

from contextlib import contextmanager
import subprocess
import threading
import requests
import tempfile
import socket
import psutil
import signal
import pytest
import time
import sys
import os


@contextmanager
def config_file(content):
    fle = None
    try:
        fle = tempfile.NamedTemporaryFile(delete=False)
        with open(fle.name, "w") as fle:
            fle.write(content)
        yield fle.name
    finally:
        if fle and os.path.exists(fle.name):
            os.remove(fle.name)


class Container_managerAssertionsMixin:
    class Manager:
        def __init__(self):
            self.shutdowns = []

        def port_connected(self, port):
            s = socket.socket()
            s.settimeout(5)
            try:
                s.connect(("127.0.0.1", port))
                s.close()
                return True
            except Exception:
                return False

        def pid_running(self, pid):
            return pid in [p.pid for p in psutil.process_iter()]

        def assertPIDGoneWithin(self, pid, timeout):
            start = time.time()
            while time.time() - start < timeout:
                if not self.pid_running(pid):
                    return
                time.sleep(0.1)

            assert not self.pid_running(pid)

        def free_port(self):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", 0))
                return s.getsockname()[1]

        def local(self, port, path):
            return "http://localhost:{0}{1}".format(port, path)

        def wait_for_pid(self, pid, timeout=5):
            start = time.time()
            while time.time() - start < timeout:
                if self.pid_running(pid):
                    return
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.1)

            if self.pid_running(pid):
                os.kill(pid, signal.SIGKILL)

        def wait_for_file(self, filename, timeout=5):
            start = time.time()
            while time.time() - start < timeout:
                if os.path.exists(filename):
                    return
                time.sleep(0.1)

            if not os.path.exists(filename):
                assert False, "Failed to wait for filename: {0}".format(filename)

        def wait_for_port(self, port, timeout=2):
            start = time.time()
            while time.time() - start < timeout:
                if self.port_connected(port):
                    return
                time.sleep(0.1)

            assert self.port_connected(port)

        def assertForks(self, info, timeout=1):
            start = time.time()
            while time.time() - start < timeout:
                if info["done"]:
                    return

            if not info["done"]:
                assert False, "The process should have forked, but it hasn't within timeout"

        def version(self, info):
            return requests.get(self.local(info["port"], "/version")).content.decode()

        def start_inprocess(self, manager):
            port = self.free_port()
            server = make_server(manager, ("127.0.0.1", port))
            self.shutdowns.append(server.shutdown)

            thread = threading.Thread(target=server.serve_forever)
            thread.daemon = True
            thread.start()

            self.wait_for_port(port)

            return lambda path: "http://127.0.0.1:{0}{1}".format(port, path)

        def start(self, specifier, filename=None, port=None, log_file=None, config=""):
            info = {"done": False, "pid": None, "port": port}

            def shutdown():
                if filename or not info["done"]:
                    if info["port"]:
                        requests.get("http://localhost:{0}/shutdown".format(info["port"]))
                    if info["pid"]:
                        self.wait_for_pid(info["pid"])
                if "p" in info:
                    info["p"].kill()

            self.shutdowns.append(shutdown)
            info["shutdown"] = shutdown

            def start():
                options = ""
                if log_file:
                    options = ', "--logging-handler-file", "{0}"'.format(log_file)

                with config_file(config) as cfg:
                    env = dict(os.environ)
                    env["HARPOON_CONFIG"] = cfg

                    command = (
                        'from harpoon.executor import main; main(["container_manager", "{0}"{1}])'
                    )
                    info["p"] = subprocess.Popen(
                        [sys.executable, "-c", command.format(specifier, options)], env=env
                    )
                    info["p"].wait()
                    info["done"] = True

            thread = threading.Thread(target=start)
            thread.daemon = True
            thread.start()

            if port:
                self.wait_for_port(port)

            if filename:
                self.wait_for_file(filename)
                with open(filename) as fle:
                    lines = fle.readlines()
                    assert len(lines) == 2
                    info["port"] = int(lines[0])
                    if port:
                        assert info["port"] == port
                    info["pid"] = int(lines[1])
                    assert self.pid_running(info["pid"])

            info["uri"] = lambda path: "http://localhost:{0}{1}".format(info["port"], path)
            return info

    @pytest.fixture()
    def container_manager(self):
        manager = self.Manager()

        try:
            yield manager
        finally:
            errors = []

            for shutdown in manager.shutdowns:
                try:
                    shutdown()
                except Exception as error:
                    errors.append(error)

            assert len(errors) == 0
