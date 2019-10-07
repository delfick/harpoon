# coding: spec

from harpoon.container_manager import Manager

from tests.helpers import HarpoonCase

from delfick_project.norms import sb
from threading import Event
from unittest import mock
import threading
import requests
import tempfile
import pytest
import signal
import time
import uuid
import json
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


describe HarpoonCase, "locking containers":

    @pytest.fixture()
    def cm_fake_run(self, container_manager):
        harpoon = mock.NonCallableMock(name="harpoon", spec=[])
        image_puller = mock.NonCallableMock(name="image_puller", spec=[])

        pg_image = mock.NonCallableMock(name="postgres_image", spec=[])
        redis_image = mock.NonCallableMock(name="redis_image ", spec=[])

        images = {"redis": redis_image, "postgres": pg_image}

        manager = Manager(harpoon, images, image_puller)

        def send_info(request, *args, **kwargs):
            request.send_response(200)
            request.send_header("Content-Type", "application/json")
            request.end_headers()

            p = {"ports": {"6379": 5678}, "just_created": True, "container_id": "__CONTAINER_ID__"}
            request.wfile.write(json.dumps(p).encode())

        private_send_container_info = mock.Mock(name="_send_container_info", side_effect=send_info)

        private_build_and_run = mock.Mock(name="_build_and_run")

        mock.patch.object(manager, "_send_container_info", private_send_container_info).start()
        mock.patch.object(manager, "_build_and_run", private_build_and_run).start()

        uri = container_manager.start_inprocess(manager)

        yield uri, private_build_and_run

    def ask_for_images(self, uri, called, optionssets, results=None):
        events = [Event() for event in optionssets]

        def ask_for_images():
            for i, options in enumerate(optionssets):
                if isinstance(options, str):
                    options = {"image": options, "ports": [[0, 6379]]}
                elif isinstance(options, tuple):
                    options = {"image": options[0], "ports": [[0, 6379]], "lock": options[1]}

                called.append(("start_container", i))

                res = requests.post(uri("/start_container"), json=options)

                if results is not None:
                    content = res.content
                    if isinstance(content, bytes):
                        content = content.decode()
                    results.append(json.loads(content))

                called.append(("done", i))
                events[i].set()

        thread = threading.Thread(target=ask_for_images)
        thread.daemon = True
        thread.start()
        return events

    it "does not build if an image is already building", cm_fake_run:
        called = []
        uri, build_and_run = cm_fake_run

        build_event = Event()
        started_building = Event()
        cc = []

        def builder(*args, **kwargs):
            cc.append("builder")
            started_building.set()
            build_event.wait()
            cc.append("built")

        build_and_run.side_effect = builder

        start = time.time()
        event1, event2 = self.ask_for_images(uri, called, ["redis", "redis"])

        try:
            started_building.wait()

            assert cc == ["builder"]

            assert not event1.is_set()
            assert not event2.is_set()

            build_event.set()

            event1.wait(timeout=2)
            event2.wait(timeout=2)

            assert cc == ["builder", "built", "builder", "built"]
        finally:
            build_event.set()

    it "can build two types of images at the same time", cm_fake_run:
        called = []
        uri, build_and_run = cm_fake_run

        build_event = Event()
        started_building = [Event(), Event()]
        cc = []

        info = {"i": 0}

        def builder(*args, **kwargs):
            cc.append("builder")
            started_building[info["i"]].set()
            info["i"] += 1
            build_event.wait()
            cc.append("built")

        build_and_run.side_effect = builder

        start = time.time()
        (event1,) = self.ask_for_images(uri, called, ["redis"])
        (event2,) = self.ask_for_images(uri, called, ["postgres"])

        try:
            for s in started_building:
                s.wait(timeout=1)

            assert cc == ["builder", "builder"]

            assert not event1.is_set()
            assert not event2.is_set()

            build_event.set()

            event1.wait(timeout=2)
            event2.wait(timeout=2)

            assert cc == ["builder", "builder", "built", "built"]
        finally:
            build_event.set()

    it "says no if a previous build failed", cm_fake_run:
        uri, build_and_run = cm_fake_run

        def builder(*args, **kwargs):
            raise ValueError("NOPE")

        build_and_run.side_effect = builder

        results = []

        (event1,) = self.ask_for_images(uri, [], ["redis"], results=results)
        assert event1.wait(timeout=1)
        assert results[0] == {"error": {"message": "NOPE"}, "error_code": "ValueError"}

        (event2,) = self.ask_for_images(uri, [], ["redis"], results=results)
        assert event2.wait(timeout=1)
        assert results[1] == {
            "error": {"message": "Already attempted to start image and that failed"},
            "error_code": "ImageAlreadyFailed",
        }

    it "doesn't lock images by default", cm_fake_run:
        called = []
        uri, build_and_run = cm_fake_run

        event1, event2 = self.ask_for_images(uri, called, ["redis", "redis"])

        event1.wait(timeout=2)
        event2.wait(timeout=2)

    it "locked images don't lock other images", cm_fake_run:
        called = []
        uri, build_and_run = cm_fake_run

        event1, event2 = self.ask_for_images(uri, called, [("redis", True), ("postgres", True)])

        event1.wait(timeout=2)
        event2.wait(timeout=2)

    it "subsequent /start_container for locked images require an unlock", cm_fake_run:
        called = []
        uri, build_and_run = cm_fake_run
        event1, event2, event3 = self.ask_for_images(
            uri, called, [("redis", True), ("redis", True), ("redis", True)]
        )
        assert event1.wait(timeout=2), called

        requests.post(uri("/unlock_container"), json={"image": "redis"})
        assert event2.wait(timeout=2), called

        requests.post(uri("/unlock_container"), json={"image": "redis"})
        assert event3.wait(timeout=2), called

        requests.post(uri("/unlock_container"), json={"image": "redis"})

        assert called == [
            ("start_container", 0),
            ("done", 0),
            ("start_container", 1),
            ("done", 1),
            ("start_container", 2),
            ("done", 2),
        ]

    it "can still shutdown if an image is locked", cm_fake_run:
        called = []
        uri, build_and_run = cm_fake_run
        (event1,) = self.ask_for_images(uri, called, [("redis", True)])

        # Make sure event2 is after event1
        time.sleep(0.2)

        (event2,) = self.ask_for_images(uri, called, [("redis", True)])

        assert event1.wait(timeout=2), called
        time.sleep(0.2)

        assert not event2.is_set()

        requests.get(uri("/shutdown"))

        print(event2)
        assert event2.wait(timeout=2), called
        assert len(build_and_run.mock_calls) == 2
