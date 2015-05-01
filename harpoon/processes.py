"""
Some helper functions for running subprocesses and ensuring they don't hang or
stick around.
"""
from harpoon.errors import CouldntKill

import subprocess
import logging
import signal
import shlex
import fcntl
import time
import os

log = logging.getLogger("harpoon.processes")

def read_non_blocking(stream):
    """Read from a non-blocking stream"""
    if stream:
        while True:
            nxt = ''
            try:
                nxt = stream.readline()
            except IOError:
                pass

            if nxt:
                yield nxt
            else:
                break

def command_output(command, *command_extras, **kwargs):
    """Get the output from a command"""
    output = []
    cwd = kwargs.get("cwd", None)
    stdin = kwargs.get("stdin", None)
    verbose = kwargs.get("verbose", False)

    args = shlex.split(' '.join([command] + list(command_extras)))
    timeout = kwargs.get("timeout", 10)

    log.debug("Running command\targs=%s", args)
    if verbose:
        log.info("Running command\tcommand=%s", command)

    process_kwargs = {"stderr": subprocess.STDOUT, "stdout": subprocess.PIPE, "cwd": cwd}
    if stdin is not None:
        process_kwargs["stdin"] = stdin
    process = subprocess.Popen(args, **process_kwargs)

    fl = fcntl.fcntl(process.stdout, fcntl.F_GETFL)
    fcntl.fcntl(process.stdout, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    start = time.time()
    while True:
        if time.time() - start > timeout:
            break
        if process.poll() is not None:
            break
        for nxt in read_non_blocking(process.stdout):
            output.append(nxt.decode("utf8").strip())
            if verbose: print(output[-1])
        time.sleep(0.01)

    attempted_sigkill = False
    if process.poll() is None:
        start = time.time()
        log.error("Command taking longer than timeout (%s). Terminating now\tcommand=%s", timeout, args)
        process.terminate()

        while True:
            if time.time() - start > timeout:
                break
            if process.poll() is not None:
                break
            for nxt in read_non_blocking(process.stdout):
                output.append(nxt.decode("utf8").strip())
                if verbose: print(output[-1])
            time.sleep(0.01)

        if process.poll() is None:
            log.error("Command took another 5 seconds after terminate, so sigkilling it now")
            os.kill(process.pid, signal.SIGKILL)
            attempted_sigkill = True

    for nxt in read_non_blocking(process.stdout):
        output.append(nxt.decode("utf8").strip())
        if verbose: print(output[-1])

    if process.poll() is not 0 and attempted_sigkill:
        raise CouldntKill("Failed to sigkill hanging process", pid=process.pid, command=args, output="\n".join(output))

    if process.poll() != 0:
        log.error("Failed to run command\tcommand=%s", args)

    return output, process.poll()

