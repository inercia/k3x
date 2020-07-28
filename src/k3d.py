# k3d.py
#
# Copyright 2020 Alvaro Saurin
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import logging
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import datetime
from dateutil.parser import parse
from typing import Dict, Iterator, List
from typing import Optional, Tuple, Callable

from gi.repository import GObject

from .config import APP_ENV_PREFIX
from .config import ApplicationSettings
from .config import (DEFAULT_EXTRA_PATH,
                     DEFAULT_API_SERVER_PORT_RANGE,
                     DEFAULT_K3D_WAIT_TIME)
from .docker import DockerController
from .helm import HelmChart, cleanup_for_owner
from .utils import (call_in_main_thread,
                    find_unused_port_in_range,
                    parse_or_get_address,
                    find_executable,
                    run_command_stdout)
from .utils_ui import show_notification

# the header/footer length in the "k3d list" output
K3D_LIST_HEADER_LEN = 3
K3D_LIST_FOOTER_LEN = 1

# directory in the K3s conatiner where we should put manifests for being automatically loaded
K3D_DOCKER_MANIFESTS_DIR = "/var/lib/rancher/k3s/server/manifests/"

###############################################################################

k3d_exe = find_executable("k3d", extra_paths=DEFAULT_EXTRA_PATH)
logging.debug(f"k3d found at {k3d_exe}")


def run_k3d_command(*args, **kwargs) -> Iterator[str]:
    """
    Run a k3d command
    """
    logging.debug(f"[K3D] Running k3d command: {args}")
    yield from run_command_stdout(k3d_exe, *args, **kwargs)


###############################################################################
# errors
###############################################################################


class K3dError(Exception):
    """Base class for other k3d exceptions"""
    pass


class EmptyClusterNameError(K3dError):
    """No cluster name"""
    pass


class InvalidNumWorkersError(K3dError):
    """Invalid num workers"""
    pass


class ClusterCreationError(K3dError):
    """Cluster creation error"""
    pass


class ClusterDestructionError(K3dError):
    """Cluster destruction error"""
    pass


class ClusterNotFoundError(K3dError):
    """Cluster not found error"""
    pass


class NoKubeconfigObtainedError(K3dError):
    """No kubeconfig obtained error"""
    pass


class NoServerError(K3dError):
    """No Docker server error"""
    pass


###############################################################################
# k3d clusters
###############################################################################

class K3dCluster(GObject.GObject):
    name: str = ""
    status: str = "running"
    num_workers: int = 0
    use_registry: bool = False
    registry_name: str = None
    registry_port: str = None
    registry_volume: str = None
    cache_hub: bool = False
    api_server: str = None
    image: str = None
    volumes: Dict[str, str] = {}
    charts: List[HelmChart] = []
    server_args: str = None

    __gsignals__ = {
        # a signal emmited when the cluster has been created
        "created": (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, (str,)),

        # a signal emmited when the cluster has been destroyed
        "destroyed": (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, (str,))
    }

    def __init__(self, settings: ApplicationSettings, docker: DockerController, **kwargs):
        super().__init__()
        self._docker = docker
        self._settings = settings
        self._kubeconfig = None
        self._docker_created: Optional[datetime.datetime] = None
        self._docker_server_ip = None
        self._notification = None
        self._destroyed = False
        self._status = kwargs.pop("status", "running")
        self.__dict__.update(kwargs)

        # TODO: check the name is valid
        if len(self.name) == 0:
            raise InvalidNumWorkersError
        if self.num_workers < 0:
            raise InvalidNumWorkersError

    def __str__(self) -> str:
        return f"{self.name}"

    def __eq__(self, other) -> bool:
        if other is None:
            return False
        if isinstance(other, K3dCluster):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other

        logging.warning(f"Comparing cluster {self.name} to incompatible type {other}")
        return NotImplemented

    def __ne__(self, other) -> bool:
        if other is None:
            return True
        if isinstance(other, K3dCluster):
            return self.name != other.name
        if isinstance(other, str):
            return self.name != other

        logging.warning(f"Comparing cluster {self.name} to incompatible type {other}")
        return NotImplemented

    def quit(self):
        pass

    def create(self, wait=True) -> None:
        """
        Create the cluster by invoking `k3d create`
        """
        args = []
        kwargs = {}

        if not self.name:
            raise EmptyClusterNameError()

        args += [f"--name={self.name}"]

        if self.use_registry:
            args += ["--enable-registry"]
            if self.cache_hub:
                args += ["--enable-registry-cache"]
            if self.registry_volume:
                args += [f"--registry-volume={self.registry_volume}"]
            if self.registry_name:
                args += [f"--registry-name={self.registry_name}"]
            if self.registry_port:
                args += [f"--registry-port={self.registry_port}"]

        if wait:
            args += [f"--wait={DEFAULT_K3D_WAIT_TIME}"]

        if self.num_workers > 0:
            args += [f"--workers={self.num_workers}"]

        if self.image:
            args += [f"--image={self.image}"]

        # create some k3s server arguments
        # by default, we add a custom DNS domain with the same name as the cluster
        args += [f"--server-arg=--cluster-domain={self.name}.local"]
        if self.server_args:
            args += [f"--server-arg={arg}" for arg in self.server_args if len(arg) > 0]

        # append any extra volumes
        for vol_k, vol_v in self.volumes.items():
            args += [f"--volume={vol_k}:{vol_v}"]

        # append any extra Charts as volumes too
        for chart in self.charts:
            src = chart.generate(self)
            dst = f"{K3D_DOCKER_MANIFESTS_DIR}/{chart.name}.yaml"
            args += [f"--volume={src}:{dst}"]

        # use the given API port or find an unused one
        self.api_server = parse_or_get_address(self.api_server, *DEFAULT_API_SERVER_PORT_RANGE)
        logging.info(f"[K3D] Using API address {self.api_server}")
        args += [f"--api-port={self.api_server}"]

        # check if we must use an env variable for the DOCKER_HOST
        docker_host = self._docker.docker_host
        default_docker_host = self._docker.default_docker_host
        if docker_host != self._docker.default_docker_host:
            logging.debug(f"[K3D] Overriding DOCKER_HOST={docker_host} (!= {default_docker_host})")
            new_env = os.environ.copy()
            new_env["DOCKER_HOST"] = docker_host
            kwargs["env"] = new_env

        try:
            logging.info(f"[K3D] Creating cluster (with {args})")
            while True:
                try:
                    line = next(run_k3d_command("create", *args, **kwargs))
                    logging.debug(f"[K3D] {line}")

                    # detect errors in the output
                    if "level=fatal" in line:
                        raise ClusterCreationError(line.strip())
                except StopIteration:
                    break
        except Exception as e:
            logging.error(f"Could not create cluster: {e}. Cleaning up...")
            self._cleanup()
            self._destroyed = True
            raise e

        logging.info("[K3D] The cluster has been created")
        self._status = "running"

        call_in_main_thread(lambda: self.emit("created", self.name))

    def destroy(self) -> None:
        """
        Destroy this cluster with `k3d delete`
        """
        logging.info("[K3D] Destroying cluster")

        if not self.name:
            raise EmptyClusterNameError()

        if self._destroyed:
            raise ClusterDestructionError("Trying to destroy an already destroyed cluster")

        args = []
        args += [f"--name={self.name}"]
        args += ["--keep-registry-volume"]

        while True:
            try:
                line = next(run_k3d_command("delete", *args))
                logging.debug(f"[K3D] {line}")
            except StopIteration:
                break

        self._cleanup()
        self._destroyed = True
        call_in_main_thread(lambda: self.emit("destroyed", self.name))

    def _cleanup(self) -> None:
        """
        Cleanup any remaining things after destroying a cluster
        """
        logging.debug(f"[K3D] Cleaning up for {self.name}")
        cleanup_for_owner(self.name)

    @property
    def kubeconfig(self) -> Optional[str]:
        """
        Get the kubeconfig file for this cluster, or None if no
        """
        if self._destroyed:
            return None

        # cache the kubeconfig: once obtained, it will not change
        if not self._kubeconfig:
            for _ in range(0, 20):
                try:
                    line = next(run_k3d_command("get-kubeconfig", f"--name={self.name}"))
                except StopIteration:
                    break
                except subprocess.CalledProcessError:
                    logging.debug(f"[K3D] ... KUBECONFIG for {self.name} not ready yet...")
                    time.sleep(1)
                else:
                    logging.debug(f"[K3D] ... obtained KUBECONFIG for {self.name} at {line}")
                    self._kubeconfig = line
                    break

        return self._kubeconfig

    @property
    def running(self) -> bool:
        return self._status == "running"

    def start(self) -> None:
        if not self.running:
            args = []
            args += [f"--name={self.name}"]

            logging.debug(f"[K3D] Starting {self.name}...")
            while True:
                try:
                    line = next(run_k3d_command("start", *args))
                    logging.debug(f"[K3D] {line}")
                except StopIteration:
                    break

    def stop(self) -> None:
        if self.running:
            args = []
            args += [f"--name={self.name}"]

            logging.debug(f"[K3D] Stopping {self.name}...")
            while True:
                try:
                    line = next(run_k3d_command("stop", *args))
                    logging.debug(f"[K3D] {line}")
                except StopIteration:
                    break

    @property
    def docker_created(self) -> Optional[datetime.datetime]:
        if self._destroyed:
            return None

        if self._docker_created is None:
            c = self._docker.get_container_by_name(self.docker_server_name)
            if c:
                t = self._docker.get_container_created(c)
                if t:
                    try:
                        self._docker_created = parse(t)
                    except Exception as e:
                        logging.error(f"[K3D] could not parse time string {t}: {e}")

        return self._docker_created

    @property
    def docker_server_name(self) -> Optional[str]:
        if self._destroyed:
            return None

        return f"k3d-{self.name}-server"

    @property
    def docker_network_name(self) -> Optional[str]:
        if self._destroyed:
            return None

        return f"k3d-{self.name}"

    @property
    def docker_server_ip(self) -> Optional[str]:
        if self._destroyed:
            return None

        if not self._docker_server_ip:
            c = self._docker.get_container_by_name(self.docker_server_name)
            if c:
                ip = self._docker.get_container_ip(c, self.docker_network_name)
                if ip is None:
                    raise NoServerError(
                        f"could not obtain server IP for {self.docker_server_name} in network {self.docker_network_name}")
                self._docker_server_ip = ip

        return self._docker_server_ip

    @property
    def dashboard_url(self) -> Optional[str]:
        if self._destroyed:
            return None

        ip = self.docker_server_ip
        if ip:
            return f"https://{self.docker_server_ip}/"

    def check_dashboard(self, *args) -> bool:
        """
        Check that the Dashboard is ready
        """
        try:
            context = ssl._create_unverified_context()
            return urllib.request.urlopen(self.dashboard_url, context=context).getcode()
        except urllib.error.URLError as e:
            logging.info(f"Error when checking {self.dashboard_url}: {e}")
            return False

    def open_dashboard(self, *args) -> None:
        import webbrowser
        u = self.dashboard_url
        if u is not None:
            logging.debug(f"[K3D] Opening '{u}' in default web browser")
            webbrowser.open(u)
        else:
            logging.warning(f"[K3D] No URL to open")

    def show_notification(self, msg, header: str = None, icon: str = None,
                          timeout: Optional[int] = None,
                          action: Optional[Tuple[str, Callable]] = None):
        """
        Show a notification specific for this cluster.
        The notification will be saved and next invocations will show as "updates"
        """
        def do_notify():
            self._notification = show_notification(msg=msg, header=header, timeout=timeout, action=action, icon=icon,
                                                   notification=self._notification, threaded=False)
        call_in_main_thread(do_notify)

    @property
    def script_environment(self) -> Dict[str, str]:
        """
        Return a dictionary with env variables for running scripts for this cluster
        """
        # Note: make sure we do not return any non-string value or subprocess.run will throw an exception.
        env = {
            f"{APP_ENV_PREFIX}_CLUSTER_NAME": str(self.name),
        }

        if not self._destroyed:
            env.update({
                f"{APP_ENV_PREFIX}_REGISTRY_ENABLED": "1" if self.use_registry else "",
                f"{APP_ENV_PREFIX}_REGISTRY_NAME": str(self.registry_name) if self.registry_name else "",
                f"{APP_ENV_PREFIX}_REGISTRY_PORT": str(self.registry_port) if self.registry_port else "",
                f"{APP_ENV_PREFIX}_MASTER_IP": str(self.docker_server_ip) if self.docker_server_ip is not None else "",
                f"{APP_ENV_PREFIX}_KUBECONFIG": self.kubeconfig if self.kubeconfig is not None else "",
            })

        return env


GObject.type_register(K3dCluster)
