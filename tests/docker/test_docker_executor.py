# coding: spec

from __future__ import print_function

from harpoon.executor import main

from tests.helpers import HarpoonCase
from six import StringIO
import logging
import uuid
import json
import sys
import os

mtime = 1431170923

describe HarpoonCase, "Executing harpoon":
    it "executes the given task":
        content = str(uuid.uuid1())
        config = { "images":
            { "blah":
              { "commands":
                [ [ "FROM", os.environ["BASE_IMAGE"] ]
                , [ "ADD", {"content": content, "dest": "/tmp/blah", "mtime": mtime } ]
                , "CMD cat /tmp/blah"
                ]
              , "tasks":
                { "stuff": { "description": "Run the task" }
                }
              , "context": False
              }
            }
          }


        old_handlers = list(logging.getLogger("").handlers)
        try:
            with self.fake_std_streams() as (fake_stdout, fake_stderr):
                with self.a_temp_file(json.dumps(config)) as filename:
                    with self.modified_env(HARPOON_CONFIG=filename):
                        try:
                            main(["make", "blah"])
                            logging.getLogger("").handlers = list(old_handlers)
                            main(["stuff", "--silent", "--silent-build"])
                        except SystemExit as error:
                            assert False

                    self.assertEqual(open(fake_stdout.name).readlines()[-1].strip(), content)
        finally:
            logging.getLogger("").handlers = list(old_handlers)

