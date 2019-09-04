# coding: spec

from tests.helpers import HarpoonCase

from unittest import mock
import requests
import tempfile
import pytest
import signal
import os


@pytest.fixture()
def filename():
    fle = tempfile.NamedTemporaryFile(delete=False)
    os.remove(fle.name)
    return fle.name


@pytest.fixture()
def log_file():
    fle = tempfile.NamedTemporaryFile(delete=False)
    os.remove(fle.name)
    return fle.name


describe HarpoonCase, "container_manager":
    it "can fork itself, write the port of the web server and start web server in background", container_manager, filename:
        info = container_manager.start(filename, filename=filename)
        container_manager.assertForks(info)
        container_manager.wait_for_file(filename)
        with open(filename) as fle:
            port = int(fle.readlines()[0])
        assert container_manager.version(info).startswith("harpoon ")

        os.remove(filename)
        port = container_manager.free_port()
        info = container_manager.start(
            "{0}:{1}".format(filename, port), filename=filename, port=port
        )
        container_manager.assertForks(info)
        container_manager.wait_for_file(filename)
        with open(filename) as fle:
            assert int(fle.readlines()[0]) == port
        assert container_manager.version(info).startswith("harpoon ")

    it "can be given just a port", container_manager:
        port = container_manager.free_port()
        info = container_manager.start(":{0}".format(port), port=port)
        assert container_manager.version(info).startswith("harpoon ")
        assert not info["done"]

    it "defaults to not forking and using port 4545", container_manager:
        if container_manager.port_connected(4545):
            pytest.skip("Can't test if the host already is using 4545")
        info = container_manager.start(":4545", port=4545)
        assert container_manager.version(info).startswith("harpoon ")
        assert not info["done"]

    it "can be killed with sigint", container_manager, filename, log_file:
        port = container_manager.free_port()
        info = container_manager.start(":{0}".format(port), port=port, log_file=log_file)
        assert container_manager.version(info).startswith("harpoon ")
        assert not info["done"]
        pid = info["p"].pid
        with open(log_file) as fle:
            lines = fle.readlines()
            assert any("GET /version" in line for line in lines)
            assert not any("GET /shutdown" in line for line in lines)

        os.kill(pid, signal.SIGINT)
        container_manager.assertPIDGoneWithin(pid, 1)

        with open(log_file) as fle:
            lines = fle.readlines()
            assert any("GET /shutdown" in line for line in lines)

    it "can be killed with sigterm", container_manager, filename, capsys, log_file:
        port = container_manager.free_port()
        info = container_manager.start(":{0}".format(port), port=port, log_file=log_file)
        assert container_manager.version(info).startswith("harpoon ")
        assert not info["done"]
        with open(log_file) as fle:
            lines = fle.readlines()
            assert any("GET /version" in line for line in lines)
            assert not any("GET /shutdown" in line for line in lines)

        pid = info["p"].pid
        os.kill(pid, signal.SIGTERM)
        container_manager.assertPIDGoneWithin(pid, 1)

        with open(log_file) as fle:
            lines = fle.readlines()
            assert any("GET /shutdown" in line for line in lines)

    it "has a shutdown handler", container_manager:
        manager = mock.Mock(name="manager", shutting_down=False)

        def shutdown(request):
            manager.shutting_down = True
            request.send_response(204)
            request.end_headers()

        manager.shutdown.side_effect = shutdown

        uri = container_manager.start_inprocess(manager)

        res = requests.get(uri("/shutdown"))
        assert res.status_code == 204, res.content
        assert manager.shutting_down
        manager.shutdown.assert_called_once_with(mock.ANY)

        res = requests.get(uri("/shutdown"))
        assert res.status_code == 204, res.content
        assert manager.shutting_down
        manager.shutdown.assert_called_once_with(mock.ANY)

    it "has a start_container handler", container_manager:
        manager = mock.Mock(name="manager")

        def start_container(request):
            request.send_response(200)
            request.end_headers()

        manager.start_container.side_effect = start_container

        uri = container_manager.start_inprocess(manager)

        res = requests.post(uri("/start_container"))
        assert res.status_code == 200, res.content
        manager.start_container.assert_called_once_with(mock.ANY)

    it "has a stop_container handler", container_manager:
        manager = mock.Mock(name="manager")

        def stop_container(request):
            request.send_response(200)
            request.end_headers()

        manager.stop_container.side_effect = stop_container

        uri = container_manager.start_inprocess(manager)

        res = requests.post(uri("/stop_container"))
        assert res.status_code == 200, res.content
        manager.stop_container.assert_called_once_with(mock.ANY)
