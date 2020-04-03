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
from typing import Dict, Iterator, List, Optional, Union

from gi.repository import GObject

from .config import ApplicationSettings
from .config import (DEFAULT_EXTRA_PATH,
                     DEFAULT_K3D_WAIT_TIME,
                     DEFAULT_K3D_LIST_UPDATE_INTERVAL,
                     SETTINGS_KEY_REG_ADDRESS)
from .docker import DockerController
from .helm import HelmChart, cleanup_for_owner
from .kubectl import (merge_kubeconfigs_to,
                      kubectl_set_current_context,
                      kubectl_get_current_context)
from .utils import (call_in_main_thread,
                    emit_in_main_thread,
                    find_unused_port_in_range,
                    find_executable,
                    run_command_stdout,
                    call_periodically,
                    truncate_file)
from .utils_ui import show_notification

# the header/footer length in the "k3d list" output
K3D_LIST_HEADER_LEN = 3
K3D_LIST_FOOTER_LEN = 1

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
    api_port: int = None
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
        self.__dict__.update(kwargs)
        self._docker = docker
        self._settings = settings
        self._kubeconfig = None
        self._docker_server_ip = None

        # TODO: check the name is valid
        if len(self.name) == 0:
            raise InvalidNumWorkersError
        if self.num_workers < 0:
            raise InvalidNumWorkersError

    def __str__(self):
        return f"{self.name}"

    def __eq__(self, other):
        if not hasattr(other, "name"):
            return NotImplemented
        return self.name == other.name

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
            args += [f"--server-arg={arg}" for arg in self.server_args]

        # append any extra volumes
        for vol_k, vol_v in self.volumes.items():
            args += [f"--volume={vol_k}:{vol_v}"]

        # append any extra Charts as volumes too
        for chart in self.charts:
            src = chart.generate(self)
            dst = f"/var/lib/rancher/k3s/server/manifests/{chart.name}.yaml"
            args += [f"--volume={src}:{dst}"]

        # use the given API port or find an unused one
        if not self.api_port:
            self.api_port = find_unused_port_in_range(6400, 6500)
        args += [f"--api-port={self.api_port}"]

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
        except:
            self.cleanup()
            raise

        logging.info("[K3D] The cluster has been created")

        call_in_main_thread(lambda: self.emit("created", self.name))

    def destroy(self) -> None:
        """
        Destroy this cluster with `k3d delete`
        """
        if not self.name:
            raise EmptyClusterNameError()

        logging.info("[K3D] Destroying cluster")
        args = []
        args += [f"--name={self.name}"]
        args += ["--keep-registry-volume"]

        while True:
            try:
                line = next(run_k3d_command("delete", *args))
                logging.debug(f"[K3D] {line}")
            except StopIteration:
                break

        self.cleanup()

        call_in_main_thread(lambda: self.emit("destroyed", self.name))

    def cleanup(self):
        logging.debug(f"[K3D] Cleaning up for {self.name}")
        cleanup_for_owner(self.name)

    @property
    def kubeconfig(self) -> str:
        """
        Get the kuhbeconfig file for this cluster, or None if no
        """
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
    def docker_server_name(self) -> str:
        return f"k3d-{self.name}-server"

    @property
    def docker_network_name(self) -> str:
        return f"k3d-{self.name}"

    @property
    def docker_server_ip(self) -> Optional[str]:
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
    def dashboard_url(self) -> str:
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
            logging.exception(f"Error when checking {self.dashboard_url}: {e}")
            return False

    def open_dashboard(self, *args) -> None:
        import webbrowser
        logging.debug(f"[K3D] Opening '{self.dashboard_url}' in default web browser")
        webbrowser.open(self.dashboard_url)


GObject.type_register(K3dCluster)


###############################################################################
# the k3d clusters controller
###############################################################################

class K3dController(GObject.GObject):
    """
    A controller for the k3d clusters
    """

    __gsignals__ = {
        # a signal emmited when the cluster has changed
        "clusters-changed": (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, (int,)),

        # a signal emmited when the active cluster has changed
        # arguments: <cluster_name>
        "change-current-cluster": (GObject.SIGNAL_RUN_CLEANUP, GObject.TYPE_NONE, (str,)),
    }

    def __init__(self, settings: ApplicationSettings, docker: DockerController, **kwargs):
        super().__init__(*kwargs)
        self.clusters = dict()
        self._settings = settings
        self._docker = docker

        # refresh the list of clusters cached, and schedule a periodic update
        logging.debug("[K3D] Initializing K3DController...")
        self.refresh(forced_kubeconfig=True)
        call_periodically(DEFAULT_K3D_LIST_UPDATE_INTERVAL, self.refresh)

    def _k3d_list(self) -> Dict[str, K3dCluster]:
        """
        Get all the clusters currently running as a map indexed by cluster name
        """
        cs = dict()

        #  This must parse the output of `k3d list`, like:
        #
        # +-----------------+------------------------------------+---------+---------+
        # |      NAME       |               IMAGE                | STATUS  | WORKERS |
        # +-----------------+------------------------------------+---------+---------+
        # | k3s-cluster-209 | docker.io/rancher/k3s:v1.17.3-k3s1 | running |   0/0   |
        # +-----------------+------------------------------------+---------+---------+

        try:
            lines = [line for line in run_k3d_command("list")]
        except subprocess.CalledProcessError:
            # k3d fails when no clusters are found
            pass
        else:
            for line in lines[K3D_LIST_HEADER_LEN:-K3D_LIST_FOOTER_LEN]:
                components = [c.strip() for c in line.split("|") if len(c) > 0]
                if len(components) < 2:
                    logging.error(f"[K3D] could not parse output: {line}")
                    return cs

                try:
                    logging.debug(f"[K3D] Parsed components: {components}")
                    name, image, status = components[0:3]
                    logging.debug(f"[K3D] Parsed cluster info: name={name}, image={image}")
                    cs[name] = K3dCluster(settings=self._settings, docker=self._docker, name=name, image=image,
                                          status=status)
                except Exception as e:
                    logging.exception(f"[K3D] PARSER ERROR !!!! Could not parse {line}: {e}")
                    show_notification(f"Could not parse {line}: {e}", header="f{name} INTERNAL ERROR",
                                      icon="dialog-error")

        return cs

    @property
    def active(self) -> Optional[K3dCluster]:
        """
        Returns the currently active cluster name
        """
        current_cluster = kubectl_get_current_context()
        if current_cluster is None:
            logging.debug("[K3D] No current context obtained (probably no clusters exist)")
            return None

        return self.get_cluster_by_name(current_cluster)

    @active.setter
    def active(self, new_cluster: Union[K3dCluster, str]) -> None:
        current_cluster = self.active

        if new_cluster is None:
            logging.warning("[K3D] Trying to set current cluster to None")
            return

        new_cluster_name = new_cluster.name if isinstance(new_cluster, K3dCluster) else new_cluster

        if current_cluster is not None and new_cluster_name == current_cluster.name:
            logging.debug(f"[K3D] No need to switch cluster: it is the same, '{new_cluster_name}'")
            return

        if new_cluster_name not in self.clusters:
            logging.warning(f"[K3D] Trying to set as current an inexistant cluster '{new_cluster_name}'")
            return

        logging.info(f"[K3D] Switching to cluster {new_cluster_name}")
        try:
            kubectl_set_current_context(new_cluster_name)
        except Exception as e:
            logging.exception(f"[K3D] When switching to cluster {new_cluster_name}: {e}")
        else:
            emit_in_main_thread(self, "change-current-cluster", new_cluster_name)

    @property
    def kubeconfig(self) -> str:
        """
        Returns the global Kubeconfig file where all the individual Kubeconfigs will be merged
        """
        return os.path.expandvars(self._settings.get_string("kubeconfig").strip("\'").strip("\""))

    def check_local_registry(self):
        """
        Perform a check on <registry>/v2/_catalog
        """
        try:
            context = ssl._create_unverified_context()
            registry_address = self._settings.get_safe_string(SETTINGS_KEY_REG_ADDRESS)
            registry_catalog_url = f"http://{registry_address}/_v2/catalog"
            return urllib.request.urlopen(registry_catalog_url, context=context).getcode()
        except urllib.error.URLError as e:
            logging.exception(f"Error when checking {registry_catalog_url}: {e}")
            return False

    def create(self, **kwargs) -> K3dCluster:
        """
        Create a cluster, with the given attributes
        """
        cluster = K3dCluster(settings=self._settings, docker=self._docker, **kwargs)
        cluster.create()
        self.refresh()
        return cluster

    def destroy(self, name: str, **kwargs) -> None:
        """
        Delete a cluster with the given name
        """
        cluster = self.get_cluster_by_name(name)
        if cluster:
            cluster.destroy()
        self.refresh()

    def refresh(self, forced_kubeconfig=False, active_cluster: Optional[K3dCluster] = None) -> bool:
        # more advanced setup:
        #
        # NAME=$(kubectl --kubeconfig=$1 config get-contexts -o name | head -n 1)
        # kubectl config unset clusters.$NAME >/dev/null 2>&1
        # kubectl config unset users.$NAME >/dev/null 2>&1
        # kubectl config unset current-context >/dev/null 2>&1
        # kubectl config delete-context $NAME >/dev/null 2>&1
        # KUBECONFIG=~/.kube/config:$1 kubectl config view --flatten > ~/.kube/merged && cp ~/.kube/config ~/.kube/backup && mv ~/.kube/merged ~/.kube/config
        # kubectl config use-context $NAME

        def do_refresh():
            logging.info("[K3D] Updating list of clusters with 'k3d list'")
            latest_clusters = self._k3d_list()
            logging.debug("[K3D] ... {} clusters obtained".format(len(latest_clusters)))

            # save the current cluster, merge all the kubeconfigs and then activate the
            # same cluster again... in case there was an active cluster
            if active_cluster is not None:
                logging.debug(f"[K3D] Will activate cluster forced cluster {active_cluster} later on...")
                cluster_to_activate = active_cluster
            elif len(self.clusters) > 0:
                cluster_to_activate = self.active
                logging.debug(f"[K3D] Will re-activate current cluster {cluster_to_activate} later on...")
            else:
                cluster_to_activate = None

            changes = False
            try:
                if set(latest_clusters.keys()) != set(self.clusters.keys()) or \
                        not os.path.exists(self.kubeconfig) or \
                        forced_kubeconfig:

                    changes = True

                    logging.info(f"[K3D] Regenerating kubeconfig at {self.kubeconfig} " +
                                 "({} clusters)".format(len(latest_clusters)))

                    if len(latest_clusters) > 0:
                        clusters_kubeconfigs = []
                        for c in latest_clusters.values():
                            kubeconfig = c.kubeconfig
                            if not kubeconfig:
                                raise NoKubeconfigObtainedError(f"could not get a KUBECONFIG for {c.name}")
                            clusters_kubeconfigs.append(kubeconfig)

                        merge_kubeconfigs_to(clusters_kubeconfigs, self.kubeconfig)
                    else:
                        truncate_file(self.kubeconfig)

            except Exception as e:
                logging.exception(f"[K3D] Could not update kubeconfig: {e}")
            finally:
                self.clusters = latest_clusters

                if cluster_to_activate is not None:
                    self.active = cluster_to_activate

                if changes:
                    # note: no need of call_in_main_thread for this `emit`, as `inner_refresh` has
                    #       been started with call_in_main_thread
                    self.emit("clusters-changed", len(latest_clusters))

        call_in_main_thread(do_refresh)
        return True  # must return True for keeping updating

    def get_cluster_by_name(self, name: str) -> Optional[K3dCluster]:
        """
        Get a cluster by a name
        """
        try:
            return self.clusters[str(name)]
        except KeyError as e:
            return None

    def on_quit(self):
        logging.debug("[K3D] Quitting K3D controller")



GObject.type_register(K3dController)
