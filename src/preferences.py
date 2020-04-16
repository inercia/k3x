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
import socket

from gi.repository import Granite, Gtk, Gdk

from .config import (APP_ID,
                     APP_TITLE)
from .config import ApplicationSettings
from .config import (DEFAULT_AUTOSTART_ENTRY_FILE,
                     DEFAULT_PREFS_WIDTH,
                     DEFAULT_PREFS_HEIGHT)
from .config import (SETTINGS_KEY_DOCKER_ENDPOINT,
                     SETTINGS_KEY_KUBECONFIG,
                     SETTINGS_KEY_START_ON_LOGIN,
                     SETTINGS_KEY_REG_ADDRESS,
                     SETTINGS_KEY_REG_VOL,
                     SETTINGS_KEY_REG_MODE,
                     SETTINGS_KEY_CREATE_HOOK,
                     SETTINGS_KEY_DESTROY_HOOK,
                     SETTINGS_KEY_K3D_IMAGE,
                     SETTINGS_KEY_K3S_ARGS)
from .docker import is_valid_docker_name
from .utils import parse_registry, RegistryInvalidError
from .utils_ui import (SettingsPage,
                       show_error_dialog,
                       show_warning_dialog)

SETTINGS_REG_LOCAL = "Regular registry"
SETTINGS_REG_CACHE = "Only pull-through cache"


###############################################################################
# Errors
###############################################################################


class PreferencesError(Exception):
    """
    A configuration error
    """

    def __init__(self, setting, message):
        self.setting = setting
        self.message = message


class PreferencesWarning(Exception):
    """
    A configuration warning
    """

    def __init__(self, setting, message):
        self.setting = setting
        self.message = message


###############################################################################
# Startup entry
###############################################################################

class K3dvStartupEntry(object):
    contents = f"""
[Desktop Entry]
Name=k3d
Exec=flatpak run --user {APP_ID}
Terminal=false
Type=Application
Categories=System;
StartupNotify=true
X-GNOME-Autostart-enabled=true
"""

    def __init__(self):
        super(K3dvStartupEntry, self).__init__()
        self._filename = DEFAULT_AUTOSTART_ENTRY_FILE

    def create(self):
        logging.info(f"Creating/over-writting desktop entry file {self._filename}")
        with open(self._filename, "w") as out:
            out.write(self.contents)

    def delete(self):
        if os.path.exists(self._filename):
            logging.info(f"Removing desktop entry file {self._filename}")
            os.remove(self._filename)


###############################################################################
# Preferences
###############################################################################

class PreferencesDialog(Gtk.Window):

    def __init__(self, docker):
        super().__init__()

        self.set_default_size(DEFAULT_PREFS_WIDTH, DEFAULT_PREFS_HEIGHT)
        self.set_resizable(False)
        self.set_border_width(10)
        self.set_gravity(Gdk.Gravity.CENTER)
        self.set_position(Gtk.WindowPosition.CENTER)

        self._settings = ApplicationSettings(APP_ID)

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
        defaults_button.get_style_context().add_class(Gtk.STYLE_CLASS_DESTRUCTIVE_ACTION)
        self.header.pack_start(defaults_button)

        # ... and a "Apply" button
        apply_button = Gtk.Button(label="Apply")
        apply_button.connect("clicked", self.on_apply_clicked)
        apply_button.get_style_context().add_class(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
        self.header.pack_end(apply_button)

    def show_all(self):
        super(PreferencesDialog, self).show_all()
        self._settings.delay()

    def on_apply_clicked(self, *args):
        """
        The user has pressed the "Apply" button
        """
        logging.info("Applying changes in preferences")
        try:
            self.view.on_validate()
        except PreferencesError as e:
            show_error_dialog(msg="Preferences validation error", explanation=f"\n\n{e.message}")
            if e.setting is not None:
                self._settings.reset(e.setting)
            return
        except PreferencesWarning as e:
            show_warning_dialog(msg="Preferences warning", explanation=f"\n\n{e.message}")

        try:
            self.view.on_apply()
        except Exception as e:
            show_error_dialog(msg="Saving error", explanation=f"\n\n{e}")
            return

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

    def on_validate(self):
        self.general_preferences.on_validate()
        self.registry_preferences.on_validate()
        self.k3s_preferences.on_validate()
        self.hooks_preferences.on_validate()

    def on_apply(self):
        self.general_preferences.on_apply()
        self.registry_preferences.on_apply()
        self.k3s_preferences.on_apply()
        self.hooks_preferences.on_apply()

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
            "or cluster created with some other tools.")
        self.append_labeled_entry("Kubeconfig file:", self.kubeconfig_entry, SETTINGS_KEY_KUBECONFIG)

        # The docker entrypoint
        self.docker_endpoint_entry = Gtk.Entry()
        self.docker_endpoint_entry.props.hexpand = False
        self.docker_endpoint_entry.set_tooltip_text(
            "Docker endpoint, like unix:///var/run/docker.sock or "
            "tcp:192.168.1.10:1111")
        self.append_labeled_entry("Docker URL:", self.docker_endpoint_entry, SETTINGS_KEY_DOCKER_ENDPOINT)

        # Start on login
        self.start_login_checkbutton = Gtk.Switch()
        self.start_login_checkbutton.set_tooltip_text(
            f"When enabled, {APP_TITLE} is started on login")
        self.append_labeled_entry("Start on login:", self.start_login_checkbutton, SETTINGS_KEY_START_ON_LOGIN)

    def on_apply(self):
        start_on_login = self._settings.get_boolean(SETTINGS_KEY_START_ON_LOGIN)
        startup = K3dvStartupEntry()
        if start_on_login:
            startup.create()
        else:
            startup.delete()


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
        registry_mode.append([SETTINGS_REG_LOCAL])
        registry_mode.append([SETTINGS_REG_CACHE])

        self.registry_mode = Gtk.ComboBox.new_with_model(registry_mode)
        renderer_text = Gtk.CellRendererText()
        self.registry_mode.pack_start(renderer_text, True)
        self.registry_mode.add_attribute(renderer_text, "text", 0)
        self.registry_mode.set_tooltip_text(
            "When configured as a pull-through cache, the local Docker registry will act "
            "as a local cache of all the images that are downloaded "
            "from the Docker Hub, but you cannot 'push' to this registry. ")
        self.append_labeled_entry("Local registry mode:", self.registry_mode, SETTINGS_KEY_REG_MODE)

        # Registry hostname
        self.registry_name_entry = Gtk.Entry()
        self.registry_name_entry.hexpand = True
        self.append_labeled_entry("Registry Name/Port:", self.registry_name_entry, SETTINGS_KEY_REG_ADDRESS)

        # Registry volume
        self.registry_volume_entry = Gtk.Entry()
        self.registry_volume_entry.hexpand = True
        self.registry_volume_entry.set_tooltip_text("Volume for saving the images.")
        self.append_labeled_entry("Volume for images:", self.registry_volume_entry, SETTINGS_KEY_REG_VOL)

    def on_validate(self):
        """
        Validate the registry configuration
        """
        logging.debug("[PREFERENCES] Validating registry can be parsed...")
        registry_address = self._settings.get_safe_string(SETTINGS_KEY_REG_ADDRESS)
        try:
            parsed_registry = parse_registry(registry_address)
            if parsed_registry is None:
                return

            registry_name, registry_port = parsed_registry
        except RegistryInvalidError as e:
            raise PreferencesError(SETTINGS_KEY_REG_ADDRESS,
                                   f"'<b><tt>{registry_address}</tt></b>' does not seem a valid registry."
                                   "\n\n"
                                   f"'{registry_address}' could not be parsed as a valid registry <tt>ADDRESS:PORT</tt>.")

        logging.debug("[PREFERENCES] Validating registry volume...")
        registry_volume = self._settings.get_safe_string(SETTINGS_KEY_REG_VOL)
        if registry_volume is not None and len(registry_volume) > 0:
            if not is_valid_docker_name(registry_volume):
                raise PreferencesError(SETTINGS_KEY_REG_VOL,
                                       f"'<b><tt>{registry_volume}</tt></b>' does not seem a valid volume name."
                                       "\n\n"
                                       f"'{registry_volume}' is not a valid Docker volume name.")

        logging.debug("[PREFERENCES] Validating the registry address can be resolved...")
        try:
            socket.gethostbyname_ex(registry_name)
        except Exception as e:
            raise PreferencesError(SETTINGS_KEY_REG_ADDRESS,
                                   f"DNS name '<b><tt>{registry_name}</tt></b>' cannot be resolved."
                                   "\n\n"
                                   f"'{registry_name}' cannot be resolved as a valid DNS name. That usually means that either\n\n"
                                   f"1) your DNS server is not resolving this name, or"
                                   "\n\n"
                                   f"2) you must add a line like '<tt>127.0.0.1 {registry_name}</tt>' "
                                   f"in your '<tt>/etc/hosts</tt>' file.")


###############################################################################
# Advanced: K3s settings
###############################################################################

class K3sSettingsPage(SettingsPage):
    _managed_settings = [
        SETTINGS_KEY_K3D_IMAGE,
        SETTINGS_KEY_K3S_ARGS,
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
        self.k3d_image.set_tooltip_text(
            "When specified, will use an alternative Docker image for the k3d nodes."
            "See the list of official k3s images at https://hub.docker.com/r/rancher/k3s/tags")
        self.append_labeled_entry("k3d docker image:", self.k3d_image, SETTINGS_KEY_K3D_IMAGE)

        self.k3s_args = Gtk.Entry()
        self.k3s_args.hexpand = True
        self.k3s_args.set_tooltip_text(
            "When specified, will add these extra arguments to the k3s server.")
        self.append_labeled_entry("k3s server args:", self.k3s_args, SETTINGS_KEY_K3S_ARGS)


###############################################################################
# Advanced: hooks
###############################################################################

class HooksSettingsPage(SettingsPage):
    _managed_settings = [
        SETTINGS_KEY_CREATE_HOOK,
        SETTINGS_KEY_DESTROY_HOOK,
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
        self.cluster_create_hook.set_tooltip_text(
            "A script that will be run right after creating a new cluster")
        self.cluster_create_hook.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "folder-open")
        self.append_labeled_entry("After-creation script:", self.cluster_create_hook, SETTINGS_KEY_CREATE_HOOK)

        self.cluster_destroy_hook = Gtk.Entry()
        self.cluster_destroy_hook.props.hexpand = False
        self.cluster_destroy_hook.set_tooltip_text(
            "A script that will be run right after deleting a cluster")
        self.cluster_destroy_hook.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "folder-open")
        self.append_labeled_entry("After-destruction script:", self.cluster_destroy_hook, SETTINGS_KEY_DESTROY_HOOK)

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

    def on_validate(self):
        """
        Validate all the settings, raising an exception if something is wrong
        """
        logging.debug("[PREFERENCES] Validating hooks...")
        create_hook = self._settings.get_safe_string(SETTINGS_KEY_CREATE_HOOK)
        if len(create_hook) > 0:
            if not os.path.exists(create_hook):
                raise PreferencesError("cluster_create_hook",
                                       f"The create script:"
                                       "\n\n"
                                       f"<b><tt>{create_hook}</tt></b>"
                                       "\n\n"
                                       "does not exist or is not accessible.")

        destroy_hook = self._settings.get_safe_string(SETTINGS_KEY_DESTROY_HOOK)
        if len(destroy_hook) > 0:
            if not os.path.exists(destroy_hook):
                raise PreferencesError("cluster_destroy_hook",
                                       f"The destruction script:"
                                       "\n\n"
                                       f"<b><tt>{destroy_hook}</tt><b>"
                                       "\n\n"
                                       "does not exist or is not accessible.")
