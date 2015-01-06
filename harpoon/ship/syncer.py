"""
The Syncer is responsible for pushing and pulling docker images
"""

from __future__ import print_function

from harpoon.ship.progress_stream import ProgressStream, Failure, Unknown
from harpoon.errors import BadImage, ProgrammerError, FailedImage

import logging
import json
import sys

log = logging.getLogger("harpoon.ship.syncer")

########################
###   PROGRESS STREAM
########################

class BuildProgressStream(ProgressStream):
    def interpret_line(self, line_detail):
        if "status" in line_detail:
            line = line_detail["status"].strip()

        if "progressDetail" in line_detail:
            line = "{0} {1}".format(line, line_detail["progressDetail"])

        if "progress" in line_detail:
            line = "{0} {1}".format(line, line_detail["progress"])

        if line_detail and ("progressDetail" in line_detail or "progress" in line_detail):
            self.add_line("\r{0}".format(line))
        else:
            self.add_line(line)

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
        self.push_or_pull(conf, "pull", ignore_missing=ignore_missing)

    def push_or_pull(self, conf, action=None, ignore_missing=False):
        """Push or pull this image"""
        if action not in ("push", "pull"):
            raise ProgrammerError("Should have called push_or_pull with action to either push or pull, got {0}".format(action))

        if not conf.image_index:
            raise BadImage("Can't push without an image_index configuration", image=conf.name)

        sync_stream = SyncProgresStream()
        for line in getattr(conf.harpoon.docker_context, action)(conf.image_name, stream=True):
            try:
                sync_stream.feed(line)
            except Failure as error:
                if ignore_missing and action == "pull":
                    log.error("Failed to %s an image\timage=%s\timage_name=%s\tmsg=%s", action, conf.name, conf.image_name, error)
                    break
                else:
                    raise FailedImage("Failed to {0} an image".format(action), image=conf.name, image_name=conf.image_name, msg=msg)
            except Unknown as error:
                log.warning("Unknown line\tline=%s", error)

            for part in sync_stream.printable():
                sys.stdout.write(part.encode('utf-8', 'replace'))
            sys.stdout.flush()

