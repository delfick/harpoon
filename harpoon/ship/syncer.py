from __future__ import print_function

from harpoon.errors import BadImage, ProgrammerError, FailedImage

import logging
import json
import sys

log = logging.getLogger("harpoon.ship.syncer")

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

        for line in getattr(conf.harpoon.docker_context, action)(conf.image_name, stream=True):
            line_detail = None
            try:
                line_detail = json.loads(line)
            except (ValueError, TypeError) as error:
                log.warning("line from docker wasn't json", got=line, error=error)

            if line_detail:
                if "errorDetail" in line_detail:
                    msg = line_detail["errorDetail"].get("message", line_detail["errorDetail"])
                    if ignore_missing and action == "pull":
                        log.error("Failed to %s an image\timage=%s\timage_name=%s\tmsg=%s", action, conf.name, conf.image_name, msg)
                    else:
                        raise FailedImage("Failed to {0} an image".format(action), image=conf.name, image_name=conf.image_name, msg=msg)
                if "status" in line_detail:
                    line = line_detail["status"].strip()

                if "progressDetail" in line_detail:
                    line = "{0} {1}".format(line, line_detail["progressDetail"])

                if "progress" in line_detail:
                    line = "{0} {1}".format(line, line_detail["progress"])

            if line_detail and ("progressDetail" in line_detail or "progress" in line_detail):
                sys.stdout.write("\r{0}".format(line))
                sys.stdout.flush()
            else:
                print(line)

