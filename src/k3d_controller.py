# k3d_controller.py
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
import urllib.error
import urllib.request
from typing import Dict, Union
from typing import Optional

from gi.repository import GObject

from .config import ApplicationSettings, APP_ENV_PREFIX
from .config import (DEFAULT_K3D_LIST_UPDATE_INTERVAL,
                     SETTINGS_KEY_REG_ADDRESS)
from .docker import DockerController
from .k3d import (K3dCluster,
                  run_k3d_command,
                  NoKubeconfigObtainedError)
from .kubectl import (merge_kubeconfigs_to,
                      kubectl_set_current_context,
                      kubectl_get_current_context)
from .utils import (call_in_main_thread,
                    emit_in_main_thread,
                    call_periodically,
                    truncate_file,
                    run_hook_script, ScriptError)
from .utils_ui import show_notification, show_error_dialog

# the header/footer length in the "k3d list" output
K3D_LIST_HEADER_LEN = 3
K3D_LIST_FOOTER_LEN = 1


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
        self._active = None

        # refresh the list of clusters cached, and schedule a periodic update
        logging.debug("[K3D] Initializing K3DController...")
        self.refresh(initial=True)
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
                    logging.debug(f"[K3D] Parsed cluster info: name={name}, image={image}, status={status}")
                    cs[name] = K3dCluster(settings=self._settings, docker=self._docker,
                                          name=name, image=image, status=status)
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
        return self._active

    @active.setter
    def active(self, new_cluster: Union[K3dCluster, str]) -> None:
        if new_cluster is None:
            if len(self.clusters) > 0:
                logging.debug("[K3D] No active cluster")

            if self._active is not None:
                emit_in_main_thread(self, "change-current-cluster", None)
            self._active = None
            return

        new_cluster_name = new_cluster.name if isinstance(new_cluster, K3dCluster) else new_cluster

        if self._active is not None and new_cluster_name == self._active.name:
            logging.debug(f"[K3D] No need to switch cluster: it is the same, '{new_cluster_name}'")
            return

        if new_cluster_name not in self.clusters:
            logging.info(f"[K3D] Active cluster '{new_cluster_name}' is not known: probably not a K3D cluster")
            if self._active is not None:
                emit_in_main_thread(self, "change-current-cluster", None)
            self._active = None
            return

        logging.info(f"[K3D] Switching to cluster '{new_cluster_name}'")
        try:
            kubectl_set_current_context(new_cluster_name, kubeconfig=self.kubeconfig)
        except Exception as e:
            logging.exception(f"[K3D] When switching to cluster '{new_cluster_name}': {e}")
        else:
            self._active = self.get_cluster_by_name(new_cluster_name)
            emit_in_main_thread(self, "change-current-cluster", new_cluster_name)

    @property
    def kubeconfig(self) -> str:
        """
        Returns the global Kubeconfig file where all the individual Kubeconfigs will be merged
        """
        return os.path.expandvars(self._settings.get_safe_string("kubeconfig"))

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

    def create(self, activate=False, **kwargs) -> Optional[K3dCluster]:
        """
        Create a cluster, with the given attributes

        NOTE: this method will be called in a Thread
        """
        name = kwargs.get("name")
        post_create_hook = kwargs.pop("post_create_hook", None)

        if not self._docker.valid:
            show_error_dialog(msg=f"Could not connect to Docker at {self._docker.docker_host}",
                              explanation=f"Please check that\n\n"
                                          "1) Docker is installed and running\n"
                                          f"3) '<tt>{self._docker.docker_host}</tt>' exists and is accessible\n"
                                          "3) the Docker URL in the <b><i>Preferences</i></b> is correct.")
            return None

        try:
            cluster = K3dCluster(settings=self._settings, docker=self._docker, **kwargs)
        except Exception as e:
            show_notification(f"Cluster {name} creation failed: {e}.", header="f{name} ERROR",
                              icon="dialog-error")
            return None

        cluster.show_notification(f"{cluster.name} is being created in the background",
                                  header=f"{cluster.name} CREATING...")
        try:
            cluster.create()
        except Exception as e:
            cluster.show_notification(f"Cluster {name} creation failed: {e}.", header="f{name} ERROR",
                                      icon="dialog-error")
        else:
            cluster.show_notification(
                f"{name} has been successfully created. Server is available at {cluster.dashboard_url}",
                header=f"{name} CREATED",
                action=("Dashboard", cluster.open_dashboard))
        finally:
            active_cluster = None
            if activate:
                active_cluster = cluster

            self.refresh(active_cluster=active_cluster)

        if post_create_hook:
            cluster.show_notification(f"Running post-creation script '{post_create_hook}' in the background.",
                                      header=f"Running post-create script")
            try:
                env = cluster.script_environment
                env[f"{APP_ENV_PREFIX}_ACTION"] = "create"
                run_hook_script(post_create_hook, env=env)
            except ScriptError as e:
                show_notification(f"Cluster {name} post-creation script failed: {e}.",
                                  header=f"Script error", icon="dialog-error")
                logging.exception(f"Cluster {name} post-creation script '{post_create_hook}' failed: {e}.")

        return cluster

    def destroy(self, name: str, **kwargs) -> None:
        """
        Delete a cluster with the given name

        NOTE: this method will be called in a Thread
        """
        cluster = self.get_cluster_by_name(name)
        if cluster is None:
            return

        post_destroy_hook = kwargs.pop("post_destroy_hook", None)

        cluster.show_notification(f"{cluster.name} is being destroyed in the background",
                                  header=f"{cluster.name} DESTROYING...")
        if cluster:
            try:
                cluster.destroy()
            except Exception as e:
                cluster.show_notification(f"Cluster {name} destruction failed: {e}.",
                                          header=f"{name} ERROR", icon="dialog-error")
            else:
                cluster.show_notification(f"{name} has been destroyed.", header=f"{name} DESTROYED")
            finally:
                self.refresh()

            if post_destroy_hook:
                cluster.show_notification(f"Running post-destruction script '{post_destroy_hook}' in the background.",
                                          header=f"Running post-destroy script")
                try:
                    env = cluster.script_environment
                    env[f"{APP_ENV_PREFIX}_ACTION"] = "destroy"
                    run_hook_script(post_destroy_hook, env=env)
                except ScriptError as e:
                    cluster.show_notification(f"Cluster {name} post-destruction script failed: {e}.",
                                              header=f"Script error", icon="dialog-error")
                    logging.exception(f"Cluster {name} post-creation script '{post_destroy_hook}' failed: {e}.")

    def refresh(self, initial=False, active_cluster: Optional[K3dCluster] = None) -> bool:
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
            cluster_name_to_activate: Optional[str] = None
            if active_cluster is not None:
                logging.debug(f"[K3D] Will activate cluster forced cluster {active_cluster.name} later on...")
                cluster_name_to_activate = active_cluster.name
            elif initial:
                cluster_name_to_activate = kubectl_get_current_context(kubeconfig=self.kubeconfig)
                logging.debug(
                    f"[K3D] First time we refresh KUBECONFIG: will save currently active cluster {cluster_name_to_activate}...")
            elif len(self.clusters) > 0 and self.active is not None:
                cluster_name_to_activate = self.active.name
                logging.debug(f"[K3D] Saving current cluster {cluster_name_to_activate} for later on...")

            changes = False
            try:
                if set(latest_clusters.keys()) != set(self.clusters.keys()) or \
                        not os.path.exists(self.kubeconfig) or \
                        initial:

                    changes = True

                    cl = len(latest_clusters)
                    logging.info(f"[K3D] Regenerating kubeconfig at {self.kubeconfig} ({cl} clusters)")

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

            # update the currently active cluster
            if cluster_name_to_activate is not None and cluster_name_to_activate in self.clusters:
                self.active = cluster_name_to_activate
            else:
                self.active = kubectl_get_current_context(kubeconfig=self.kubeconfig)

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
