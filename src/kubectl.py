# kubectl.py
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
import subprocess
import tempfile
from typing import Iterator, List, Optional

from .config import DEFAULT_EXTRA_PATH
from .utils import find_executable, run_command_stdout, truncate_file

###############################################################################

kubectl_exe = find_executable("kubectl", extra_paths=DEFAULT_EXTRA_PATH)


def run_kubectl_command(*args, **kwargs) -> Iterator[str]:
    """
    Run a kubectl command
    """
    kubeconfig = kwargs.pop("kubeconfig", None)
    if kubeconfig:
        env = kwargs.pop("env", os.environ.copy())
        env["KUBECONFIG"] = kubeconfig
        kwargs["env"] = env

    logging.debug(f"[KUBECTL] Running kubectl command {args} {kwargs}")

    # IMPORTANT: remember to "consume" this iterator, or this will not be run at all
    yield from run_command_stdout(kubectl_exe, *args, **kwargs)


def merge_kubeconfigs_to(kubeconfigs: List[str], dest: str):
    """
    Merge a list of Kubeconfig to a unified Kubeconfig
    """
    logging.info(f"[KUBECTL] Merging kubeconfigs to {dest}")
    truncate_file(dest)
    kubeconfig_str = ":".join(kubeconfigs)
    with open(dest, "w") as out:
        env = os.environ.copy()
        env["KUBECONFIG"] = kubeconfig_str
        args = [kubectl_exe, "config", "view", "--merge", "--flatten"]
        p = subprocess.Popen(args, stdout=out, env=env)
        return_code = p.wait()
        if return_code:
            raise subprocess.CalledProcessError(return_code, args)


def kubectl_apply_manifest(manifest, kubeconfig=None, **kwargs) -> Iterator[str]:
    """
    Apply a manifest with `kubectl apply -f` (using a temporary file)
    """
    with tempfile.NamedTemporaryFile() as fp:
        fp.write(manifest)

        args = ["apply", "-f", fp.name]

        # IMPORTANT: remember to "consume" this iterator, or this will not be run at all
        yield from run_kubectl_command(*args, kubeconfig=kubeconfig, **kwargs)


def kubectl_get_current_context() -> Optional[str]:
    """
    Get the currently active context
    """
    try:
        lines = [line for line in run_kubectl_command("config", "current-context")]
    except subprocess.CalledProcessError as e:
        logging.warning(f"Could not obtain the current context with kubectl: {e}")
        return None

    return lines[0]


def kubectl_set_current_context(context) -> None:
    """
    Run `kubectl config use-context my-cluster-name`
    """
    try:
        lines = [line for line in run_kubectl_command("config", "use-context", context)]
    except subprocess.CalledProcessError as e:
        logging.exception(f"Could not set the current context with kubectl: {e}")
        return None
