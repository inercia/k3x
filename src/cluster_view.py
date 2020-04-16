# cluster_view.py
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
import random
import threading
from typing import Optional

from gi.repository import Granite, Gtk, Gdk

from .config import (APP_ID,
                     DEFAULT_API_SERVER,
                     SETTINGS_KEY_REG_VOL,
                     SETTINGS_KEY_REG_MODE,
                     SETTINGS_KEY_REG_ADDRESS,
                     SETTINGS_KEY_CREATE_HOOK,
                     SETTINGS_KEY_DESTROY_HOOK,
                     SETTINGS_KEY_K3D_IMAGE,
                     SETTINGS_KEY_K3S_ARGS)
from .config import ApplicationSettings
from .config import (DEFAULT_CLUSTER_VIEW_WIDTH,
                     DEFAULT_CLUSTER_VIEW_HEIGHT)
from .helm import get_charts_for_cluster
from .k3d import K3dCluster
from .k3d_controller import K3dController
from .preferences import (SETTINGS_REG_CACHE)
from .utils import parse_registry
from .utils_ui import (SettingsPage,
                       show_warning_dialog)


###############################################################################
# A view for a K3d cluster
###############################################################################

class ClusterDialog(Gtk.Window):

    def __init__(self, controller: K3dController,
                 cluster: Optional[K3dCluster] = None):
        super().__init__()
        self.set_default_size(DEFAULT_CLUSTER_VIEW_WIDTH, DEFAULT_CLUSTER_VIEW_HEIGHT)
        self.set_resizable(False)
        self.set_border_width(10)
        self.set_gravity(Gdk.Gravity.CENTER)
        self.set_position(Gtk.WindowPosition.CENTER)

        self._settings = ApplicationSettings(APP_ID)
        # Changes the Settings object into ‘delay-apply’ mode. In this mode,
        # changes to self are not immediately propagated to the backend, but kept
        # locally until Settings.apply() is called.
        # https://lazka.github.io/pgi-docs/Gio-2.0/classes/Settings.html#Gio.Settings.delay
        self._settings.delay()

        self.cluster = cluster
        self._controller = controller

        self.view = ClusterPanedView(cluster=cluster, settings=self._settings)
        self.add(self.view)

        if cluster:
            title = f"Cluster {cluster.name}"
        else:
            title = f"New k3d cluster"

        self.header = Gtk.HeaderBar()
        self.header.set_show_close_button(False)
        self.header.set_title(title)
        self.header.get_style_context().remove_class('header-bar')
        self.header.get_style_context().add_class('titlebar')
        self.header.get_style_context().add_class('background')
        self.set_titlebar(self.header)

        # add a "Cancel" button
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", self.on_cancel_clicked)
        self.header.pack_start(cancel_button)

        # ... and a "Create"/"Delete" button (depending wether the cluster already existed or not)
        if cluster is None:
            create_button = Gtk.Button(label="Create")
            create_button.connect("clicked", self.on_create_clicked)
            create_button.get_style_context().add_class(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
            self.header.pack_end(create_button)
        else:
            delete_button = Gtk.Button(label="Delete")
            delete_button.get_style_context().add_class(Gtk.STYLE_CLASS_DESTRUCTIVE_ACTION)
            delete_button.connect("clicked", self.on_delete_clicked)
            self.header.pack_end(delete_button)

            if self._controller.active != cluster:
                switch_button = Gtk.Button(label="Switch to")
                switch_button.get_style_context().add_class(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
                switch_button.connect("clicked", self.on_switch_clicked)
                self.header.pack_end(switch_button)

    ####################################
    # signal receivers
    ####################################

    def on_create_clicked(self, *args):
        """
        The "Create" button has been pressed in the "New Cluster" dialog
        """
        logging.info("[VIEW] Create clicked")
        self.create_async(activate=True)  # we always switch to the new cluster on interactive creation
        self._settings.apply()
        self.close()

    def on_delete_clicked(self, *args):
        """
        The user has pressed the "Delete" button
        """
        logging.info("[VIEW] Delete clicked: showing confirmation dialog")
        delete_diag = Granite.MessageDialog.with_image_from_icon_name("Destroy cluster?",
                                                                      "Are you sure you want to destroy this cluster?",
                                                                      "dialog-warning",
                                                                      Gtk.ButtonsType.OK_CANCEL)

        button_delete = Gtk.Button(label="Delete")
        button_delete.get_style_context().add_class(Gtk.STYLE_CLASS_DESTRUCTIVE_ACTION)
        delete_diag.add_action_widget(button_delete, Gtk.ResponseType.OK)

        button_cancel = Gtk.Button(label="Cancel")
        button_cancel.get_style_context().add_class(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        delete_diag.add_action_widget(button_cancel, Gtk.ResponseType.CANCEL)

        delete_diag.set_transient_for(self)
        delete_diag.set_flags = Gtk.DialogFlags.MODAL

        delete_diag.show_all()
        response = delete_diag.run()
        delete_diag.destroy()

        if response == Gtk.ResponseType.OK:
            self.delete_async()
        self.close()

    def on_switch_clicked(self, *args):
        logging.info(f"[VIEW] Switching to {self.cluster}")
        self._controller.active = self.cluster
        self.close()

    def on_cancel_clicked(self, *args):
        self._settings.revert()
        self.close()

    ####################################
    # properties
    ####################################

    @property
    def cluster_name(self) -> str:
        return str(self.view.general_settings.cluster_name_entry.get_text())

    def set_random_name(self) -> None:
        self.view.general_settings.set_random_name()

    @property
    def registry(self) -> str:
        return self._settings.get_safe_string(SETTINGS_KEY_REG_ADDRESS)

    @property
    def num_workers(self) -> int:
        return self.view.general_settings.num_workers.get_value_as_int()

    @property
    def use_registry(self) -> bool:
        return self.view.registry_settings.enable_registry_checkbutton.get_active()

    @property
    def registry_volume(self):
        return self._settings.get_safe_string(SETTINGS_KEY_REG_VOL)

    @property
    def cache_hub(self) -> bool:
        return self._settings.get_safe_string(SETTINGS_KEY_REG_MODE) == SETTINGS_REG_CACHE

    @property
    def api_server(self) -> str:
        s = str(self.view.network_settings.api_binding_entry.get_text())
        if s == DEFAULT_API_SERVER:
            return ""
        return s

    @property
    def install_dashboard(self) -> bool:
        return self.view.advanced_settings.install_dashboard.get_active()

    @property
    def server_args(self) -> str:
        return self._settings.get_safe_string(SETTINGS_KEY_K3S_ARGS)

    @property
    def image(self) -> str:
        return self._settings.get_safe_string(SETTINGS_KEY_K3D_IMAGE)

    @property
    def post_create_hook(self) -> str:
        return self._settings.get_safe_string(SETTINGS_KEY_CREATE_HOOK)

    @property
    def post_destroy_hook(self) -> str:
        return self._settings.get_safe_string(SETTINGS_KEY_DESTROY_HOOK)

    ####################################
    # create/delete
    ####################################

    def create_async(self, activate=False):
        """
        Create a cluster in the background with the attributes shown in this window
        """
        registry_name, registry_port = parse_registry(self.registry)

        kwargs = {"name": self.cluster_name,
                  "num_workers": self.num_workers,
                  "use_registry": self.use_registry,
                  "registry_name": registry_name,
                  "registry_port": registry_port,
                  "registry_volume": self.registry_volume,
                  "cache_hub": self.cache_hub,
                  "image": self.image,
                  "api_port": self.api_server,
                  "charts": get_charts_for_cluster(self),
                  "server_args": self.server_args,
                  "volumes": {},
                  "post_create_hook": self.post_create_hook,
                  "activate": activate
                  }

        logging.debug("[VIEW] Creating in a new thread...")
        thread = threading.Thread(target=self._controller.create, kwargs=kwargs)
        thread.daemon = True
        thread.start()

    def delete_async(self):
        """
        Delete in the background the cluster that is shown in this window
        """
        kwargs = {
            "post_destroy_hook": self.post_destroy_hook,
        }

        logging.debug("[VIEW] Destroying in a new thread...")
        thread = threading.Thread(target=self._controller.destroy, args=(self.cluster_name,), kwargs=kwargs)
        thread.daemon = True
        thread.start()


###############################################################################
# Layout
###############################################################################

class ClusterPanedView(Gtk.Paned):
    def __init__(self, settings: ApplicationSettings, cluster: Optional[K3dCluster] = None):
        super().__init__()
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self.set_hexpand(True)

        self._settings = settings

        self.general_settings = GeneralSettingsPage(cluster=cluster, settings=settings)
        self.registry_settings = RegistrySettingsPage(cluster=cluster, settings=settings)
        self.network_settings = NetworkSettingsPage(cluster=cluster, settings=settings)
        self.advanced_settings = AdvancedSettingsPage(cluster=cluster, settings=settings)

        self.stack = Gtk.Stack()
        self.stack.set_halign(Gtk.Align.FILL)
        self.stack.set_valign(Gtk.Align.FILL)
        self.stack.set_hexpand(True)
        self.stack.set_homogeneous(True)
        self.stack.add_named(self.general_settings, "settings_page")
        self.stack.add_named(self.registry_settings, "registry_page")
        self.stack.add_named(self.network_settings, "ports_page")
        self.stack.add_named(self.advanced_settings, "advanced_page")
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(100)

        self.settings_sidebar = Granite.SettingsSidebar(stack=self.stack)

        self.add(self.settings_sidebar)
        self.add(self.stack)


###############################################################################
# General settings
###############################################################################

class GeneralSettingsPage(SettingsPage):
    _managed_settings = [
        "last-num-workers",
    ]

    def __init__(self, settings: ApplicationSettings, **kwargs):
        self.cluster = kwargs.pop("cluster", None)
        super().__init__(settings=settings,
                         activatable=False,
                         description="General cluster properties",
                         header="Cluster properties",
                         icon_name="preferences-desktop",
                         title="General",
                         **kwargs)

        # The cluster name label/entry
        self.cluster_name_entry = Gtk.Entry()
        self.cluster_name_entry.props.hexpand = False
        self.cluster_name_entry.set_tooltip_text(
            "The name assigned to the cluster. It must consist in alpha, "
            "numbers and '-' and '_', like 'k3s-cluster-444'")
        self.append_labeled_entry("Cluster Name:", self.cluster_name_entry)

        # Number of workers
        self.num_workers = Gtk.SpinButton()
        self.num_workers.set_adjustment(Gtk.Adjustment(0, 0, 100, 1, 10, 0))
        self.num_workers.set_tooltip_text(
            "The number of extra workers in the cluster. k3d will start just one "
            "master. This master will be used for running your workload as well, "
            "but you can start extra workers in cluster for having something "
            "more similar to a production cluster.")
        self.num_workers.props.hexpand = False
        self.append_labeled_entry("Number of workers", self.num_workers, setting="last-num-workers")

        if self.cluster:
            box = Gtk.Box(spacing=6)

            # Current IP address
            ip_label = Gtk.Label(f"{self.cluster.docker_server_ip}")
            ip_label.props.hexpand = False
            ip_label.props.halign = Gtk.Align.START
            box.pack_start(ip_label, True, True, 0)

            def _open_dashboard(*args):
                if self.cluster.check_dashboard():
                    self.cluster.open_dashboard()
                else:
                    show_warning_dialog(msg="No web service available",
                                        explanation="\n"
                                                    f"There is no Dashboard or web service listening at\n\n"
                                                    f"<i><tt>{self.cluster.dashboard_url}</tt></i>\n\n"
                                                    "This usually means that\n\n"
                                                    "a) the Dashboard was not installed\n"
                                                    "b) it was installed but it has not started yet.\n\n"
                                                    "If you expected the Dashboard to be available, "
                                                    "please wait and try again in a while...")

            open_button = Gtk.Button(label="Open")
            open_button.connect("clicked", _open_dashboard)
            box.pack_start(open_button, True, True, 0)

            self.append_labeled_entry("Server IP address", box)

        # Disable everything if the cluster already exists
        if self.cluster is not None:
            self.num_workers.set_sensitive(False)
            self.cluster_name_entry.set_sensitive(False)
            self.cluster_name_entry.set_text(self.cluster.name)
        else:
            self.set_random_name()

    def set_random_name(self):
        r = random.randrange(0, 1000)
        self.cluster_name_entry.set_text(f"k3s-cluster-{r}")


###############################################################################
# Settings for the registry
###############################################################################

class RegistrySettingsPage(SettingsPage):
    _managed_settings = [
        "last-enable-registry",
    ]

    def __init__(self, settings: ApplicationSettings, **kwargs):
        self.cluster = kwargs.pop("cluster", None)
        super().__init__(settings=settings,
                         activatable=False,
                         description="Local registry",
                         icon_name="folder-remote",
                         title="Registry",
                         **kwargs)

        # The registry enabled/disabled
        self.enable_registry_checkbutton = Gtk.Switch()
        self.enable_registry_checkbutton.set_tooltip_text(
            "When enabled, the cluster will be connected to a local Docker registry "
            "that will be created on-demand. You will be able to push to this "
            "registry from your laptop, and images will be available "
            "in the Kubernetes cluster.")
        self.append_labeled_entry("Enable local registry:",
                                  self.enable_registry_checkbutton,
                                  setting="last-enable-registry")

        # Disable everything if the cluster already exists
        if self.cluster is not None:
            self.enable_registry_checkbutton.set_sensitive(False)
        else:
            self.enable_registry_checkbutton.set_sensitive(True)


###############################################################################
# Settings for the network
###############################################################################

class NetworkSettingsPage(SettingsPage):
    _managed_settings = [
        "last-api-address",
    ]

    def __init__(self, settings: ApplicationSettings, **kwargs):
        self.cluster = kwargs.pop("cluster", None)
        super().__init__(settings=settings,
                         activatable=False,
                         description="Network settings: ports, addresses...",
                         icon_name="preferences-system-network",
                         title="Network",
                         **kwargs)

        # The API port
        self.api_binding_entry = Gtk.Entry()
        self.api_binding_entry.hexpand = True
        self.api_binding_entry.text = "preferences-system-network"
        self.api_binding_entry.set_tooltip_text(
            "API server binding address and port. It can be "
            "[host:]port. (where a port 0 means a random port). "
            "Examples: ':6443', '0.0.0.0:6443'")
        self.append_labeled_entry("API address/port:", self.api_binding_entry,
                                  setting="last-api-address")

        # Disable everything if the cluster already exists
        if self.cluster is not None:
            self.api_binding_entry.set_sensitive(False)
        else:
            self.api_binding_entry.set_sensitive(True)


###############################################################################
# Advanced settings
###############################################################################

class AdvancedSettingsPage(SettingsPage):
    _managed_settings = [
        "last-install-dashboard",
    ]

    def __init__(self, settings: ApplicationSettings, **kwargs):
        self.cluster = kwargs.pop("cluster", None)
        super().__init__(settings=settings,
                         activatable=False,
                         description="Advanced settings",
                         icon_name="preferences-system",
                         title="Advanced",
                         **kwargs)

        # The dashboard enabled/disabled
        self.install_dashboard = Gtk.Switch()
        self.install_dashboard.set_tooltip_text(
            "When enabled, installs the Dashboard after creating the cluster.")
        self.append_labeled_entry("Install Dashboard:", self.install_dashboard, setting="last-install-dashboard")

        # Disable everything if the cluster already exists
        if self.cluster is not None:
            self.install_dashboard.set_sensitive(False)
        else:
            self.install_dashboard.set_sensitive(True)
