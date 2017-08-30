"""
The Syncer is responsible for pushing and pulling docker images
"""

from __future__ import print_function

from harpoon.ship.progress_stream import ProgressStream, Failure, Unknown
from harpoon.errors import BadImage, ProgrammerError, FailedImage
from harpoon.ship.builder import Builder

from input_algorithms.spec_base import NotSpecified
from contextlib import contextmanager
import logging
import json
import six
import sys

log = logging.getLogger("harpoon.ship.syncer")

########################
###   PROGRESS STREAM
########################

class SyncProgressStream(ProgressStream):
    def setup(self):
        self.last_id = None
        self.last_status = None

    def interpret_line(self, line_detail):
        if "aux" in line_detail:
            self.add_line('\n' + str(line_detail["aux"]) + '\n')
            return

        if "status" not in line_detail:
            self.add_line(str(line_detail) + '\n')
            return

        status = line_detail["status"]
        if "progress" in line_detail or "progressDetail" in line_detail:
            if 'id' in line_detail:
                next_id = line_detail["id"]

            progress_detail = ""
            if line_detail.get('progress'):
                progress_detail = ": {0}".format(line_detail["progress"])

            line = "{0} - {1}{2}".format(status, next_id, progress_detail)
            if next_id == self.last_id and status == self.last_status:
                line = "\r{0}".format(line)
            else:
                line = "\n{0}".format(line)

            self.last_id = next_id
        else:
            line = "\n{0}".format(status)
            self.last_id = None

        self.add_line(line)
        self.last_status = status

########################
###   SYNCER
########################

class Syncer(object):
    """Knows how to push and pull images"""

    def push(self, conf):
        """Push this image"""
        self.push_or_pull(conf, "push")

    def pull(self, conf, ignore_missing=False):
        """Push this image"""
        with Builder().remove_replaced_images(conf):
            self.push_or_pull(conf, "pull", ignore_missing=ignore_missing)

    def push_or_pull(self, conf, action=None, ignore_missing=False):
        """Push or pull this image"""
        if action not in ("push", "pull"):
            raise ProgrammerError("Should have called push_or_pull with action to either push or pull, got {0}".format(action))

        if not conf.image_index:
            raise BadImage("Can't {0} without an image_index configuration".format(action), image=conf.name)

        if conf.image_name == "scratch":
            log.warning("Not pulling/pushing scratch, this is a reserved image!")
            return

        sync_stream = SyncProgressStream()

        for attempt in range(3):
            if attempt > 0:
                log.info("Attempting sync again\taction=%s\tattempt=%d", action, attempt)

            # Login before pulling or pushing
            # Have this in the for loop incase it fails and the push/pull also fails as a result
            conf.login(conf.image_name, is_pushing=action=='push')

            try:
                for line in getattr(conf.harpoon.docker_api, action)(
                        conf.image_name
                        , tag = None if conf.tag is NotSpecified else conf.tag
                        , stream = True
                        ):

                    for line in line.split(six.binary_type("\r\n", "utf-8")):
                        if not line:
                            continue

                        try:
                            sync_stream.feed(line)
                        except Failure as error:
                            if ignore_missing and action == "pull":
                                log.error("Failed to %s an image\timage=%s\timage_name=%s\tmsg=%s", action, conf.name, conf.image_name, error)
                                break
                            else:
                                raise FailedImage("Failed to {0} an image".format(action), image=conf.name, image_name=conf.image_name, msg=error)
                        except Unknown as error:
                            log.warning("Unknown line\tline=%s", error)

                        for part in sync_stream.printable():
                            if six.PY3:
                                conf.harpoon.stdout.write(part)
                            else:
                                conf.harpoon.stdout.write(part.encode('utf-8', 'replace'))
                        conf.harpoon.stdout.flush()

                # And stop the loop!
                break

            except KeyboardInterrupt:
                raise
            except FailedImage as error:
                log.exception(error)
                if attempt == 2:
                    raise
