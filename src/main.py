# main.py
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
import signal

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('AppIndicator3', '0.1')
gi.require_version('Granite', '1.0')
gi.require_version('Notify', '0.7')

from gi.repository import Gtk, Gdk, AppIndicator3
from gi.repository import Notify as notify

from .config import ApplicationSettings
from .config import APP_ID, APP_TITLE, DEFAULT_LOG_LEVEL
from .docker import DockerController
from .menu import K3dvMenu
from .k3d_controller import K3dController
from .keybindings import Keybindings
from .utils_ui import show_notification

root = logging.getLogger()
root.setLevel(DEFAULT_LOG_LEVEL)
hdlr = root.handlers[0]
fmt = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
hdlr.setFormatter(fmt)


class Indicator(object):

    def __init__(self, version):
        self._version = version

        icon = ApplicationSettings.prepare_icon()
        if not icon:
            raise Exception("no icon found")
        logging.info(f"[MAIN] Using icon {icon}")

        logging.info("[MAIN] Starting appindicator.Indicator")
        self._indicator = AppIndicator3.Indicator.new(APP_ID,
                                                      icon,
                                                      AppIndicator3.IndicatorCategory.SYSTEM_SERVICES)
        self._indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self._indicator.set_attention_icon("indicator-messages-new")
        # self.indicator.set_label("k3d", "")

        logging.debug("[MAIN] Creating settings manager...")
        self._settings = ApplicationSettings(APP_ID)

        logging.debug("[MAIN] Creating Docker controller...")
        self._docker = DockerController(settings=self._settings)

        logging.debug("[MAIN] Creating clusters manager...")
        self._notifier = notify.init(APP_ID)
        self._controller = K3dController(settings=self._settings, docker=self._docker)

        logging.debug("[MAIN] Creating menu...")
        self._menu = K3dvMenu(controller=self._controller,
                              docker=self._docker,
                              version=self._version)
        self._indicator.set_menu(self._menu)
        self._menu.connect("quit", self.on_quit)

        logging.debug("[MAIN] Creating bindings for keyboard shortcuts...")
        self._shortcuts = {
            "New cluster": {
                "... with dialog":
                    ("new-cluster", self._menu.on_new_cluster_keystroke),
                "... with last settings":
                    ("new-cluster-defaults", self._menu.on_new_cluster_defaults_keystroke),
                "... with last settings, recycling cluster":
                    ("new-cluster-cycle", self._menu.on_new_cluster_cycle_keystroke),
            },
            "Current cluster": {
                "Open dashboard":
                    ("curr-cluster-dashboard", self._menu.on_cluster_dashboard_keystroke),
                "Destroy":
                    ("curr-cluster-destroy", None),
            }
        }
        self._menu.set_shortcuts(self._shortcuts)

        logging.debug("[MAIN] Creating bingings for keyboard shortcuts...")
        # see the data/*.gschema.xml for the keybindings settings names and defauls
        self._keybinder = Keybindings(self._settings, self._shortcuts)

        # # Get notified before menu is shown, see:
        # # https://bugs.launchpad.net/screenlets/+bug/522152/comments/15
        # self._dbusmenuitem = self.indicator.get_property('dbus-menu-server').get_property('root-node')
        # self._conn = self._dbusmenuitem.connect('about-to-show', self.on_show)

        show_notification(f"{APP_TITLE} has been started in the background. Check the k3d icon in the system tray",
                          header=f"{APP_TITLE} started")

    @property
    def visible(self):
        status = self._indicator.get_status()
        return status == AppIndicator3.IndicatorStatus.ACTIVE

    def destroy(self):
        self._indicator.destroy()

    def on_quit(self, *args, **kwargs):
        logging.debug("[MAIN] Quitting the main")
        Gtk.main_quit()


def main(version: str):
    Gdk.threads_init()

    _indicator = Indicator(version=version)  # NOTE: assign for keeping the object alive

    Gtk.Settings.get_default().set_property("gtk-icon-theme-name", "elementary")

    Gtk.main()


if __name__ == "__main__":
    main()
