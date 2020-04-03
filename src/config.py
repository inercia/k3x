# config.py
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
from shutil import copyfile

from gi.repository import GLib, Gtk, Gio

CURR_DIR = os.path.dirname(os.path.realpath(__file__))

###############################################################################
# Application info and credits
###############################################################################

APP_ID = "com.github.inercia.k3dv"
APP_DESCRIPTION = "A k3d manager"
APP_TITLE = "k3dv"
APP_VERSION = "0.1"
APP_MAIN_AUTHORS = [
    "Alvaro Saurin <alvaro.saurin@gmail.com>"
]

# NOTE: icons copied to the flatpak are not accessible in the indicator: they
#       are confined in the flatpak container.
APP_ICON_NAME = APP_ID
APP_ICON_PATH = os.path.join(
    '/app', 'share', 'icons', 'elementary', 'apps', 'scalable', APP_ID + ".svg")

# ,prefix for all the environment variables we export
APP_ENV_PREFIX = "K3DV"

APP_DOCUMENTERS = [
    "Alvaro Saurin <alvaro.saurin@gmail.com>"
]
APP_URL = "http://github.com/inercia/k3dv"
APP_COPYRIGHT = f"""
Copyright (c) 2020 {APP_MAIN_AUTHORS}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

APP_ARTISTS_CREDITS = [
    'Icons made by <a href="https://www.flaticon.es/autores/freepik" title="Freepik">Freepik</a> from <a href="https://www.flaticon.es/" title="Flaticon">www.flaticon.es</a>'
]

###############################################################################
# settings keys
###############################################################################

SETTINGS_KEY_START_ON_LOGIN = "start-on-login"

# settings key for the currently preallocated cluster
SETTINGS_KEY_PREALLOC_CLUSTER = "preallocated"

SETTINGS_KEY_DOCKER_ENDPOINT = "docker-endpoint"

SETTINGS_KEY_KUBECONFIG = "kubeconfig"

SETTINGS_KEY_REG_ADDRESS = "registry-address"

SETTINGS_KEY_REG_VOL = "registry-volume"

SETTINGS_KEY_REG_MODE = "registry-mode"


###############################################################################
# settings
###############################################################################

class ApplicationSettings(object):
    """
    The settings class
    """

    def __init__(self, schema):
        self._settings = Gio.Settings.new(schema)

        # Changes the Settings object into ‘delay-apply’ mode. In this mode,
        # changes to self are not immediately propagated to the backend, but kept
        # locally until Settings.apply() is called.
        # https://lazka.github.io/pgi-docs/Gio-2.0/classes/Settings.html#Gio.Settings.delay
        self._settings.delay()

    def __getattr__(self, name):
        method = getattr(self._settings, name)
        return method

    def get_safe_string(self, key: str) -> str:
        """
        Get a string but stripping any quotes
        """
        return str(self._settings.get_string(key)).strip("\'").strip("\"")

    def get_keybinding(self, key: str) -> str:
        """
        Get a keybinding
        """
        if not key.startswith("key-"):
            key = f"key-{key}"
        return self.get_safe_string(key)

    @staticmethod
    def get_config_dir() -> str:
        """
        Return a directory for configuration of the application
        """
        # see https://developer.gnome.org/glib/stable/glib-Miscellaneous-Utility-Functions.html#g-get-user-config-dir
        config_dir = GLib.get_user_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        return config_dir

    @staticmethod
    def get_kube_dir() -> str:
        # see https://developer.gnome.org/glib/stable/glib-Miscellaneous-Utility-Functions.html#g-get-home-dir
        home_dir = GLib.get_home_dir()
        return os.path.join(home_dir, ".kube")

    @staticmethod
    def get_cache_dir() -> str:
        # see https://developer.gnome.org/glib/stable/glib-Miscellaneous-Utility-Functions.html#g-get-user-cache-dir
        user_cache_dir = GLib.get_user_cache_dir()
        return user_cache_dir

    @staticmethod
    def get_source_app_icon():
        """
        Return the source for the indicator icon.
        """
        path = None

        if APP_ICON_PATH:
            path = APP_ICON_PATH
        elif APP_ICON_NAME:
            icon_theme = Gtk.IconTheme.get_default()
            resolution = 64
            icon = icon_theme.lookup_icon(APP_ICON_NAME, resolution, 0)
            if icon:
                path = icon.get_filename()
            else:
                logging.info(f"FATAL: icon file not found for {APP_ICON_NAME}")

        return path

    @staticmethod
    def get_app_icon() -> str:
        """
        Returns a host-accessible path to the application icon
        """
        path = ApplicationSettings.get_source_app_icon()
        dst = None
        if path:
            extension = os.path.splitext(path)[1]
            dst = os.path.join(ApplicationSettings.get_cache_dir(), "icons", "app" + extension)
            dst = os.path.abspath(dst)
        return dst

    @staticmethod
    def prepare_icon() -> str:
        """
        Prepare the indicator icon, copying it to a directory that
        is accessible from the host.
        """
        dst = None
        path = ApplicationSettings.get_source_app_icon()
        if path:
            dst = ApplicationSettings.get_app_icon()
            if os.path.exists(dst):
                os.remove(dst)

            logging.info(f"Copying icon file from {path} to {dst}")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            copyfile(path, dst)

        return dst


###############################################################################
# Defaults
###############################################################################

# the default kubeconfig file
DEFAULT_KUBECONFIG = os.path.join(ApplicationSettings.get_kube_dir(), "config")

# default API server binding address:port
DEFAULT_API_SERVER = ":0"

# the log level
DEFAULT_LOG_LEVEL = logging.DEBUG

# extra paths for looking for exes
DEFAULT_EXTRA_PATH = ["/app"]

# timeout for all the scripts that we can run
DEFAULT_SCRIPTS_TIMEOUT = 60

# a common part for the name of all the clusters created
DEFAULT_CLUSTERS_NAME_PREFIX = "k3s-cluster"

# time to wait for the cluster to be ready
DEFAULT_K3D_WAIT_TIME = 60

# "k3d list" update interval (in milliseconds)
DEFAULT_K3D_LIST_UPDATE_INTERVAL = 10000
