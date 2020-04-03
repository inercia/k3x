# utils.py
#
# MIT License
#
# Copyright (c) 2020 Alvaro Saurin <alvaro.saurin@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import logging
import os
import random
import subprocess
import threading
from typing import Iterator, Callable

from gi.repository import GLib, GObject

from .config import DEFAULT_SCRIPTS_TIMEOUT


###############################################################################
# Errors
###############################################################################

class ScriptError(Exception):
    """
    An error happened when running the script
    """
    pass


class RegistryInvalidError(Exception):
    """
    An error happened when parsing a registry
    """
    pass


###############################################################################
# subprocesses
###############################################################################


def run_command_stdout(*args, **kwargs) -> Iterator[str]:
    stdout = kwargs.pop("stdout", subprocess.PIPE)
    stderr = kwargs.pop("stderr", subprocess.PIPE)

    if stdout != subprocess.PIPE:
        logging.debug(f"[UTILS] Running process while redirecting output to {stdout.name}")

    p = subprocess.Popen(args, stdout=stdout, stderr=stderr, universal_newlines=True, **kwargs)

    if stdout == subprocess.PIPE:
        for stdout in iter(p.stdout.readline, ""):
            yield stdout.strip()
        # p.stdout.close()
        # p.stderr.close()

    return_code = p.wait()
    if return_code:
        raise subprocess.CalledProcessError(returncode=return_code, cmd=args,
                                            output="\n".join(p.stderr.readlines()))


def run_hook_script(script, env):
    """
    Run a hook script.

    NOTE: this must be called in a Thread for not blocking
    """
    logging.info(f"[UTILS] Running script {script}")
    try:
        subprocess.run([script],
                       capture_output=False,
                       timeout=DEFAULT_SCRIPTS_TIMEOUT)
    except subprocess.CalledProcessError as e:
        raise ScriptError(e)
    except subprocess.TimeoutExpired as e:
        raise ScriptError(f"timeout {DEFAULT_SCRIPTS_TIMEOUT} expired when running {script}")


def running_on_main_thread() -> bool:
    thread_name = threading.currentThread().name
    return thread_name == "MainThread"


###############################################################################
# network utils
###############################################################################


def is_port_in_use(port):
    """
    Check if a porty is in use.
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def find_unused_port_in_range(start, end):
    """
    Return a port that is not used in the given range
    """
    rang = end - start
    assert (rang > 0)

    # try random ports (for up to `rang` times)
    for _ in range(0, rang):
        maybe_port = start + random.randrange(0, rang)
        if not is_port_in_use(maybe_port):
            return maybe_port
    return None


###############################################################################
# OS utils
###############################################################################

def find_executable(executable, extra_paths=[]):
    """
    Find the path fo4r the executable provided, or None if it cannot be found.
    """
    paths = os.environ['PATH'].split(":")
    paths += extra_paths

    for path in paths:
        execname = os.path.join(path, executable)
        if os.path.isfile(execname):
            return execname

    return None


def call_periodically(period, function):
    """
    Call some function periodically
    """
    GLib.timeout_add(period, function)


def call_in_main_thread(c: Callable, *args):
    GObject.idle_add(c, *args)


def truncate_file(f):
    with open(f, "w") as fp:
        fp.truncate(0)


def emit_in_main_thread(sender: GObject, signal_name: str, *args):
    call_in_main_thread(lambda: sender.emit(signal_name, *args))


###############################################################################
# parsers
###############################################################################

def parse_registry(registry: str):
    # verify that the registry specification is valid (ie, something like "registry:5000")
    if len(registry) == 0:
        return

    try:
        registry_name, registry_port = registry.split(":")
    except:
        raise RegistryInvalidError("invalid format for registry")

    if len(registry_name) == 0:
        raise RegistryInvalidError("no registry name specified")

    if len(registry_port) == 0:
        raise RegistryInvalidError("no registry port specified")

    return registry_name, registry_port
