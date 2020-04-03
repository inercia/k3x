# preferences.py
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

from gi.repository import Granite, Gtk, Gdk

from .config import APP_TITLE
from .config import (SETTINGS_KEY_DOCKER_ENDPOINT,
                     SETTINGS_KEY_KUBECONFIG,
                     SETTINGS_KEY_START_ON_LOGIN,
                     SETTINGS_KEY_REG_ADDRESS,
                     SETTINGS_KEY_REG_VOL,
                     SETTINGS_KEY_REG_MODE)
from .utils_ui import (SettingsPage,
                       show_error_dialog,
                       show_warning_dialog)

SETTINGS_REG_NONE = "No local registry"
SETTINGS_REG_LOCAL = "Regular registry"
SETTINGS_REG_CACHE = "Only pull-through cache"


###############################################################################
# Errors
###############################################################################

class PreferencesError(Exception):
    """
    A configuration error
    """
    pass


class PreferencesWarning(Exception):
    """
    A configuration warning
    """
    pass


###############################################################################
# Preferences
###############################################################################

class PreferencesDialog(Gtk.Window):

    def __init__(self, settings, docker):
        super().__init__()

        self.set_default_size(600, 450)
        self.set_resizable(False)
        self.set_border_width(10)
        self.set_gravity(Gdk.Gravity.CENTER)
        self.set_position(Gtk.WindowPosition.CENTER)

        self._settings = settings
        self._docker = docker

        self.view = PreferencesPanedView(settings=self._settings, docker=self._docker)
        self.add(self.view)

        self.header = Gtk.HeaderBar()
        self.header.set_show_close_button(False)
        self.header.set_title("Preferences")
        self.header.get_style_context().remove_class('header-bar')
        self.header.get_style_context().add_class('titlebar')
        self.header.get_style_context().add_class('background')
        self.set_titlebar(self.header)

        # add a "Cancel" button
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", self.on_cancel_clicked)
        self.header.pack_start(cancel_button)

        # add a "Defaults" button
        defaults_button = Gtk.Button(label="Defaults")
        defaults_button.connect("clicked", self.on_defaults_clicked)
        defaults_button.get_style_context().add_class(
            Gtk.STYLE_CLASS_DESTRUCTIVE_ACTION)
        self.header.pack_start(defaults_button)

        # ... and a "Apply" button
        apply_button = Gtk.Button(label="Apply")
        apply_button.connect("clicked", self.on_apply_clicked)
        apply_button.get_style_context().add_class(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        self.header.pack_end(apply_button)

    def on_apply_clicked(self, *args):
        """
        The user has pressed the "Apply" button
        """
        logging.info("Applying changes in preferences")
        try:
            self.view.validate()
        except PreferencesError as e:
            show_error_dialog(msg="Preferences validation error", explanation=f"{e}")
            return
        except PreferencesWarning as e:
            show_warning_dialog(msg="Preferences warning", explanation=f"{e}")

        self._settings.apply()
        self.hide()

    def on_defaults_clicked(self, *args):
        """
        The user has pressed the "Defaults" button
        """
        logging.info("Resetting to default values")
        self.view.set_defaults()

    def on_cancel_clicked(self, *args):
        """
        The user has pressed the "Cancel" button
        """
        logging.info("Preferences changed canceled: reverting changes")
        self._settings.revert()
        self.hide()


# Things that could be configurable:
# TODO: keyboard shortcuts
# TODO: auto Helm charts
# TODO: auto deployed manifests (see https://rancher.com/docs/k3s/latest/en/advanced/)
# TODO: viewer for clusters (ie, Lens, chrome...)


class PreferencesPanedView(Gtk.Paned):
    """
    Panel for preferences
    """

    def __init__(self, settings, docker):
        super().__init__()
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self.set_hexpand(True)

        self._settings = settings
        self._docker = docker

        self.general_preferences = GeneralSettingsPage(settings=self._settings, docker=self._docker)
        self.registry_preferences = RegistrySettingsPage(settings=self._settings, docker=self._docker)
        self.k3s_preferences = K3sSettingsPage(settings=self._settings, docker=self._docker)
        self.hooks_preferences = HooksSettingsPage(settings=self._settings, docker=self._docker)

        self.stack = Gtk.Stack()
        self.stack.set_halign(Gtk.Align.FILL)
        self.stack.set_valign(Gtk.Align.FILL)
        self.stack.set_hexpand(True)
        self.stack.set_homogeneous(True)
        self.stack.add_named(self.general_preferences, "settings_page")
        self.stack.add_named(self.registry_preferences, "registry_page")
        self.stack.add_named(self.k3s_preferences, "k3s_page")
        self.stack.add_named(self.hooks_preferences, "hooks_page")

        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(100)

        self.settings_sidebar = Granite.SettingsSidebar(stack=self.stack)

        self.add(self.settings_sidebar)
        self.add(self.stack)

    def validate(self):
        self.general_preferences.validate()
        self.registry_preferences.validate()
        self.k3s_preferences.validate()
        self.hooks_preferences.validate()

    def set_defaults(self):
        self.general_preferences.set_defaults()
        self.registry_preferences.set_defaults()
        self.k3s_preferences.set_defaults()
        self.hooks_preferences.set_defaults()


###############################################################################
# General settings
###############################################################################

class GeneralSettingsPage(SettingsPage):
    _managed_settings = [
        SETTINGS_KEY_KUBECONFIG,
        SETTINGS_KEY_DOCKER_ENDPOINT,
        SETTINGS_KEY_START_ON_LOGIN,
    ]

    def __init__(self, **kwargs):
        self._docker = kwargs.pop("docker", None)

        super().__init__(activatable=False,
                         description="General settings",
                         header="General",
                         icon_name="preferences-desktop",
                         title="General",
                         **kwargs)

        # The Kubeconfig
        self.kubeconfig_entry = Gtk.Entry()
        self.kubeconfig_entry.props.hexpand = False
        self.kubeconfig_entry.props.halign = Gtk.Align.START
        self.kubeconfig_entry.set_tooltip_text(
            "The KUBECONFIG file. You should use something like "
            "~/.kube/config for having it automatically loaded by kubectl. "
            "It is important to note that this file WILL BE OVERWRITTEN. "
            "You should choose a different file if you are using some cloud providers "
            " or cluster created with some other tools.")
        self.append_labeled_entry("Kubeconfig file:", self.kubeconfig_entry, SETTINGS_KEY_KUBECONFIG)

        # The docker entrypoint
        self.docker_endpoint_entry = Gtk.Entry()
        self.docker_endpoint_entry.props.hexpand = False
        self.docker_endpoint_entry.props.halign = Gtk.Align.START
        self.docker_endpoint_entry.set_tooltip_text(
            "Docker endpoint, like unix:///var/run/docker.sock or "
            "tcp:192.168.1.10:1111")
        self.append_labeled_entry("Docker URL:", self.docker_endpoint_entry, SETTINGS_KEY_DOCKER_ENDPOINT)

        # Start on login
        self.start_login_checkbutton = Gtk.Switch()
        self.start_login_checkbutton.props.halign = Gtk.Align.START
        self.start_login_checkbutton.set_tooltip_text(
            f"When enabled, {APP_TITLE} is started on login")
        self.append_labeled_entry("Start on login:", self.start_login_checkbutton, SETTINGS_KEY_START_ON_LOGIN)


###############################################################################
# Advanced settings: common settings for the registry
###############################################################################

class RegistrySettingsPage(SettingsPage):
    _managed_settings = [
        SETTINGS_KEY_REG_MODE,
        SETTINGS_KEY_REG_ADDRESS,
        SETTINGS_KEY_REG_VOL,
    ]

    def __init__(self, **kwargs):
        self._docker = kwargs.pop("docker", None)

        super().__init__(activatable=False,
                         description="Local registry",
                         header="Advanced settings",
                         icon_name="folder-remote",
                         title="Registry",
                         **kwargs)

        registry_mode = Gtk.ListStore(str)
        registry_mode.append([SETTINGS_REG_NONE])
        registry_mode.append([SETTINGS_REG_LOCAL])
        registry_mode.append([SETTINGS_REG_CACHE])

        self.registry_mode = Gtk.ComboBox.new_with_model(registry_mode)
        renderer_text = Gtk.CellRendererText()
        self.registry_mode.pack_start(renderer_text, True)
        self.registry_mode.add_attribute(renderer_text, "text", 0)
        self.registry_mode.set_tooltip_text(
            "When used as a pull-through cache, the local Docker registry will act "
            "as a local cache of all the images that are downloaded "
            "from the Docker Hub, but you cannot push to this registry.")
        self.append_labeled_entry("Local registry mode:", self.registry_mode, SETTINGS_KEY_REG_MODE)

        # Registry hostname
        self.registry_name_entry = Gtk.Entry()
        self.registry_name_entry.hexpand = True
        self.registry_name_entry.text = "preferences-system"
        self.append_labeled_entry("Registry Name/Port:", self.registry_name_entry, SETTINGS_KEY_REG_ADDRESS)

        # Registry volume
        self.registry_volume_entry = Gtk.Entry()
        self.registry_volume_entry.hexpand = True
        self.registry_volume_entry.text = "preferences-system"
        self.registry_volume_entry.set_tooltip_text("Volume for saving the images.")
        self.append_labeled_entry("Volume for images:", self.registry_volume_entry, SETTINGS_KEY_REG_VOL)

        def on_registry_mode_changed(combo):
            tree_iter = combo.get_active_iter()
            if tree_iter is not None:
                model = combo.get_model()
                new_mode = model[tree_iter][0]
                if new_mode == SETTINGS_REG_NONE:
                    logging.debug("[PREF] Disabling registry settings")
                    self.registry_name_entry.set_sensitive(False)
                    self.registry_volume_entry.set_sensitive(False)
                else:
                    logging.debug("[PREF] Enabling registry settings")
                    self.registry_name_entry.set_sensitive(True)
                    self.registry_volume_entry.set_sensitive(True)

        self.registry_mode.connect("changed", on_registry_mode_changed)


###############################################################################
# Advanced: K3s settings
###############################################################################

class K3sSettingsPage(SettingsPage):
    _managed_settings = [
        "k3d-image",
        "k3s-args",
    ]

    def __init__(self, **kwargs):
        self._docker = kwargs.pop("docker", None)

        super().__init__(activatable=False,
                         description="k3s server settings",
                         icon_name="preferences-system",
                         title="K3s",
                         **kwargs)

        images_store = Gtk.ListStore(str)
        logging.debug(f"Adding k3d images in the Docker Hub")
        images_store.append([""])  # empty Docker image
        for image in self._docker.get_official_k3s_images():
            try:
                name = image.attrs["RepoTags"][0]
                logging.debug(f"... image {name}")
            except Exception as e:
                logging.debug(f"Could not grab information for image {image}: {e}")
            else:
                images_store.append([name])  # use `name` for id and... name

        self.k3d_image = Gtk.ComboBox.new_with_model_and_entry(images_store)
        renderer_text = Gtk.CellRendererText()
        self.k3d_image.pack_start(renderer_text, True)
        self.k3d_image.add_attribute(renderer_text, "text", 0)
        self.k3d_image.hexpand = True
        self.k3d_image.props.halign = Gtk.Align.START
        self.k3d_image.set_tooltip_text(
            "When specified, will use an alternative Docker image for the k3d nodes."
            "See the list of official k3s images at https://hub.docker.com/r/rancher/k3s/tags")
        self.append_labeled_entry("k3d docker image:", self.k3d_image, "k3d-image")

        self.k3s_args = Gtk.Entry()
        self.k3s_args.hexpand = True
        self.k3s_args.props.halign = Gtk.Align.START
        self.k3s_args.set_tooltip_text(
            "When specified, will add these extra arguments to the k3s server.")
        self.append_labeled_entry("k3s server args:", self.k3s_args, "k3s-args")


###############################################################################
# Advanced: hooks
###############################################################################

class HooksSettingsPage(SettingsPage):
    _managed_settings = [
        "cluster-create-hook",
        "cluster-destroy-hook",
    ]

    def __init__(self, **kwargs):
        self._docker = kwargs.pop("docker", None)

        super().__init__(activatable=False,
                         description="Scripts to run at some moments",
                         icon_name="folder",
                         title="Scripts",
                         **kwargs)

        self.cluster_create_hook = Gtk.Entry()
        self.cluster_create_hook.props.hexpand = False
        self.cluster_create_hook.props.halign = Gtk.Align.START
        self.cluster_create_hook.set_tooltip_text(
            "A script that will be run right after creating a new cluster")
        self.cluster_create_hook.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "folder-open")
        self.append_labeled_entry("After-creation script:", self.cluster_create_hook, "cluster-create-hook")

        self.cluster_destroy_hook = Gtk.Entry()
        self.cluster_destroy_hook.props.hexpand = False
        self.cluster_destroy_hook.props.halign = Gtk.Align.START
        self.cluster_destroy_hook.set_tooltip_text(
            "A script that will be run right after deleting a cluster")
        self.cluster_destroy_hook.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "folder-open")
        self.append_labeled_entry("After-destruction script:", self.cluster_destroy_hook, "cluster-destroy-hook")

        def select_file(entry, icon_pos, event, *args):
            dialog = Gtk.FileChooserDialog("Please choose a script",
                                           self.get_toplevel(),
                                           Gtk.FileChooserAction.OPEN,
                                           (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                            Gtk.STOCK_OPEN, Gtk.ResponseType.OK))

            filter_text = Gtk.FileFilter()
            filter_text.set_name("Shell")
            filter_text.add_mime_type("text/x-shellscript")
            dialog.add_filter(filter_text)

            filter_any = Gtk.FileFilter()
            filter_any.set_name("Any files")
            filter_any.add_pattern("*")
            dialog.add_filter(filter_any)

            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                filename = dialog.get_filename()
                logging.debug(f"File selected as hook: {filename}")
                if entry == self.cluster_destroy_hook:
                    self.cluster_destroy_hook.set_text(dialog.get_filename())
                elif entry == self.cluster_create_hook:
                    self.cluster_create_hook.set_text(dialog.get_filename())
            elif response == Gtk.ResponseType.CANCEL:
                logging.debug("No hook selected")

            dialog.destroy()

        self.cluster_create_hook.connect("icon-press", select_file)
        self.cluster_destroy_hook.connect("icon-press", select_file)

    def validate(self):
        """
        Validate all the settings, raising an exception if something is wrong
        """
        create_hook = self.cluster_create_hook.get_text()
        if len(create_hook) > 0:
            if not os.path.exists(create_hook):
                raise PreferencesError(f"The create script\n\n {create_hook} \n\ndoes not exist or is not accessible")

        destroy_hook = self.cluster_destroy_hook.get_text()
        if len(destroy_hook) > 0:
            if not os.path.exists(destroy_hook):
                raise PreferencesError(
                    f"The destruction script\n\n {destroy_hook} \n\ndoes not exist or is not accessible")
