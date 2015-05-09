import logging
import json

log = logging.getLogger("harpoon.ship.progress_stream")

class Failure(Exception): pass
class Unknown(Exception): pass

class ProgressStream(object):
    def __init__(self, silent_cached=False):
        self.buf = []
        self.cached = None
        self.silent_cached = silent_cached
        if hasattr(self, "setup"):
            self.setup()

    def feed(self, line):
        log.debug(line)
        line_detail = None
        try:
            line_detail = json.loads(line.decode('utf-8'))
        except (ValueError, TypeError) as error:
            log.warning("line from docker wasn't json\tgot=%s\terror=%s", line, error)
            return

        if "errorDetail" in line_detail:
            raise Failure(line_detail["errorDetail"].get("message", line_detail["errorDetail"]))

        self.interpret_line(line_detail)

    def interpret_line(self, line_detail):
        raise NotImplementedError()

    def interpret_unknown(self, line_detail):
        raise Unknown(line_detail)

    def add_line(self, line):
        if not self.silent_cached or not self.cached:
            self.buf.append(line)

    def printable(self):
        for line in self.buf:
            yield line
        self.buf = []

