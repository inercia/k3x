# menu.py
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

from gi.repository import Gtk, GdkPixbuf, GObject

from .cluster_view import ClusterDialog
from .config import (APP_ID,
                     APP_DESCRIPTION,
                     APP_TITLE,
                     APP_MAIN_AUTHORS,
                     APP_DOCUMENTERS,
                     APP_URL,
                     APP_COPYRIGHT,
                     APP_ARTISTS_CREDITS)
from .config import ApplicationSettings
from .k3d import K3dError
from .k3d_controller import K3dController
from .preferences import PreferencesDialog
from .utils import (emit_in_main_thread,
                    call_periodically,
                    call_in_main_thread,
                    running_on_main_thread)
from .utils_ui import show_notification, show_error_dialog

# menu update interval (in milli-seconds)
MENU_UPDATE_INTERVAL = 10000

# keyboard shortcuts window dimensions
KEYBOARD_SHORTCUTS_WINDOW_WIDTH = 500
KEYBOARD_SHORTCUTS_WINDOW_HEIGHT = 300


###############################################################################
# The menu
###############################################################################


class K3dvMenu(Gtk.Menu):
    __gtype_name__ = 'K3dvMenu'

    __gsignals__ = {
        # a signal emmited when we want to quit
        "quit": (GObject.SIGNAL_RUN_LAST, GObject.TYPE_NONE, (int,)),
    }

    def __init__(self, controller: K3dController, docker, version, **kwargs):
        super().__init__(**kwargs)

        self._settings = ApplicationSettings(APP_ID)
        self._docker = docker
        self._controller = controller
        self._shortcuts = None
        self._latest_clusters = dict()
        self._version = version

        self._controller.connect("clusters-changed", self.on_clusters_changed)
        self._controller.connect("change-current-cluster", self.on_active_cluster_changed)

        self.default_entries = {
            "New cluster...": (self.on_new_cluster_clicked, None),
            "New cluster with last settings": (self.on_new_cluster_defaults_clicked, None),
            "Preferences": (self.on_preferences_clicked, None),
            "Keyboard shortcuts": (self.on_shortcuts_clicked, None),
            "About": (self.on_about_clicked, None),
            "Quit": (self.on_quit_clicked, None),
        }

        # add the default entries and separator
        for label, info in self.default_entries.items():
            connection, icon = info
            if icon is not None:
                entry = Gtk.ImageMenuItem.new_from_stock("preferences-system-symbolic", None)
            else:
                entry = Gtk.MenuItem(label=label)
            entry.connect("activate", connection)
            self.append(entry)
        self.show_all()

        # create the preferences dialog but do not show it
        # this `inits` all the bindings that PreferencesDialog.__init__() creates
        self._preferences = PreferencesDialog(docker=self._docker)

        self._controller.refresh()
        self.refresh()
        call_periodically(MENU_UPDATE_INTERVAL, self.refresh)

    def set_shortcuts(self, shortcuts):
        """
        Sets the keyboard shortcuts for the "Shortcuts Help" window
        """
        self._shortcuts = shortcuts

    def refresh(self, forced=False):
        """
        Refresh the menu, removing old entries and adding the new ones.
        """
        # check if the clusters have changed
        current_clusters = self._controller.clusters
        if set(current_clusters.keys()) != set(self._latest_clusters.keys()) or forced:
            logging.info("[MENU] Clusters have changed: updating menu...")
            children = self.get_children_map()

            # remove all the entries in the menu
            for label, child in children.items():
                if (label in current_clusters.keys()) or (label in self.default_entries):
                    continue
                if isinstance(child, Gtk.SeparatorMenuItem) and len(current_clusters) > 0:
                    continue

                logging.info(f"[MENU] Menu item '{label}' is no longer valid: removing")
                self.remove(child)

            if len(current_clusters) > 0:
                if len(self._latest_clusters) == 0:
                    separator = Gtk.SeparatorMenuItem()
                    self.append(separator)

                logging.info("[MENU] Showing {} clusters in the menu".format(len(current_clusters)))
                # show an entry for each existing k3d cluster
                for cluster in current_clusters.values():
                    if cluster.name not in children:
                        cluster_menu_item = Gtk.MenuItem(label=cluster.name)
                        cluster_menu_item.connect("activate",
                                                  self.on_cluster_clicked, cluster)
                        logging.info(f"[MENU] Adding menu entry for {cluster.name}")
                        self.append(cluster_menu_item)

            self._latest_clusters = current_clusters
            self.show_all()

        return True  # must return True for keeping updating

    def get_children_map(self):
        """
        Return the children (ie, menu items) indexed by labels.
        """
        return {i.props.label: i for i in self.get_children()}

    ##################################################
    # callbacks
    ##################################################

    def on_new_cluster_clicked(self, *args):
        """
        Show the "New cluster" dialog
        """
        logging.info("[MENU] Creating new cluster...")
        new_cluster = ClusterDialog(self._controller)
        new_cluster.show_all()

    def on_new_cluster_keystroke(self, *args):
        logging.info(f"[MENU] Creating new cluster (from keystroke): {args}")
        call_in_main_thread(self.on_new_cluster_clicked)

    def on_cluster_clicked(self, widget, cluster_name):
        logging.info(f"[MENU] Cluster {cluster_name} clicked")
        # important: cluster_name is unicode: translate to str
        cluster = self._controller.get_cluster_by_name(str(cluster_name))
        if cluster:
            new_cluster = ClusterDialog(self._controller, cluster=cluster)
            new_cluster.show_all()

    def on_new_cluster_defaults_clicked(self, *args):
        """
        Create a new cluster with defaults, with the "New cluster with defaults" menu entry
        """
        logging.info("[MENU] Creating new cluster with defaults")
        new_cluster = ClusterDialog(self._controller)
        new_cluster.set_random_name()
        new_cluster.create_async(activate=True)

    def on_new_cluster_defaults_keystroke(self, *args):
        logging.info(f"[MENU] Creating new cluster with defaults (from keystroke): {args}")
        call_in_main_thread(self.on_new_cluster_defaults_clicked)

    def on_new_cluster_cycle(self, *args):
        logging.info(f"[MENU] Creating new cluster with defaults and recycling an old one: {args}")

        # choose a random cluster to remove
        clusters = self._controller.clusters
        current = self._controller.active

        if current is not None:
            logging.debug(f"[MENU] Will remove the current cluster: {current.name}")
            old_cluster_dialog = ClusterDialog(self._controller, cluster=current)
            old_cluster_dialog.delete_async()

        # check if we can activate some other random cluster
        if len(clusters) > 1:
            to_activate_name = None
            for cluster_name in clusters.keys():
                if current is None or cluster_name != current.name:
                    to_activate_name = cluster_name
                    break

            if to_activate_name is not None:
                logging.debug(f"[MENU] Will activate random cluster '{to_activate_name}'")
                self._controller.active = to_activate_name

        # create a new cluster in the background
        new_cluster = ClusterDialog(self._controller)
        new_cluster.set_random_name()
        new_cluster.create_async(activate=False)

    def on_new_cluster_cycle_keystroke(self, *args):
        logging.info(f"[MENU] Creating new cluster with defaults and recycling an old one (from keystroke): {args}")
        call_in_main_thread(self.on_new_cluster_cycle)

    def on_cluster_dashboard_keystroke(self, *args):
        active_cluster = self._controller.active
        try:
            url = active_cluster.dashboard_url
            active_cluster.show_notification(f"Opening dashboard for {active_cluster} at {url}.",
                                             header=f"Opening dashboard for {active_cluster}")
            active_cluster.open_dashboard()
        except K3dError as e:
            show_error_dialog(f"Dashboard error",
                              explanation=f"When opening dashboard for {active_cluster}: {e}.")

    def on_preferences_clicked(self, *args):
        """
        Show the "Preferences" dialog
        """
        self._preferences.show_all()

    def on_shortcuts_clicked(self, *args):
        """
        The "Shortcuts Help" menu has been clicked.
        """
        shortcuts = ShortcutsOverlay(self._settings, self._shortcuts)
        shortcuts.show_all()

    def on_about_clicked(self, *args):
        """
        The "About" menu has been clicked.
        """
        about = AboutDialog(version=self._version)
        about.show_all()

    def on_clusters_changed(self, *args):
        """
        Callback invoked when the list of clusters has changed.
        """
        logging.debug("[MENU] Received signal about changes in clusters: will refresh menu now...")
        self.refresh(forced=True)

    def on_active_cluster_changed(self, sender, cluster_name):
        """
        Callback invoked when the active cluster changes
        """
        if cluster_name is not None:
            assert running_on_main_thread()
            assert self._controller.active is not None
            self._controller.active.show_notification(f"{cluster_name} is the new active cluster.",
                                                      header=f"{cluster_name} ACTIVE")
        else:
            show_notification(f"No cluster is currently active.",
                              header=f"No cluster active")

    def on_quit_clicked(self, *args):
        """
        We are about to quit...
        """
        self._controller.on_quit()

        logging.debug("[MENU] Quitting the menu")
        emit_in_main_thread(self, "quit", 0)


###############################################################################
# The "Shortcuts" dialog
###############################################################################

class ShortcutsOverlay(Gtk.ShortcutsWindow):
    """ Window that displays the shortcuts for the active application """

    def __init__(self, settings, app_shortcuts=None):
        Gtk.ShortcutsWindow.__init__(self)

        self._settings = settings

        if app_shortcuts is None:
            app_shortcuts = {}

        self.set_default_size(KEYBOARD_SHORTCUTS_WINDOW_WIDTH,
                              KEYBOARD_SHORTCUTS_WINDOW_HEIGHT)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_modal(True)
        self.set_skip_taskbar_hint(True)

        # self.set_application(application)
        self.add_shortcuts_section(app_shortcuts)

        # always sets the default section to the "focused" app
        self.set_property("section-name", "app")

    def add_shortcuts_section(self, shortcuts=None):
        """
        Constructs the widgets required by GtkShortcutsWindow to display the application shortcuts
        """
        if not shortcuts:
            shortcuts = {}

        section = Gtk.ShortcutsSection(max_height=10, title="k3x", section_name="main")
        section.set_orientation(Gtk.Orientation.VERTICAL)
        section.show()

        for category, shortcuts in shortcuts.items():
            group = Gtk.ShortcutsGroup(title=category)
            section.add(group)

            if not shortcuts:
                continue

            for title, info in shortcuts.items():
                shortcut_id, action = info
                shortcut = self._settings.get_keybinding(shortcut_id)
                short = Gtk.ShortcutsShortcut(title=title, accelerator=shortcut)
                short.show()
                group.add(short)

        self.add(section)


###############################################################################
# The "About" dialog
###############################################################################

class AboutDialog(Gtk.AboutDialog):
    def __init__(self, version):
        Gtk.AboutDialog.__init__(self, modal=True)
        try:
            buttons = list(self.get_action_area())
            close_button = buttons[2]
            close_button.connect('clicked', lambda _: self.destroy())
            license_button = buttons[1]
            license_button.set_no_show_all(True)
        except IndexError:
            logging.exception("[MENU] GtkAboutDialog layout changed...")

        # self.set_transient_for(app_win)
        self.set_modal(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.set_license_type(Gtk.License.MIT_X11)
        self.set_copyright(APP_COPYRIGHT)
        self.set_comments(APP_DESCRIPTION)
        self.set_artists(APP_ARTISTS_CREDITS)
        self.set_wrap_license(True)
        self.set_version(version)
        self.set_program_name(APP_TITLE)

        icon_path = ApplicationSettings.get_source_app_icon()
        if icon_path:
            logo_pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_path)
            self.set_logo(logo_pixbuf.scale_simple(200, 200, GdkPixbuf.InterpType.BILINEAR))
        else:
            self.set_logo(None)

        self.set_authors(APP_MAIN_AUTHORS)
        self.set_documenters(APP_DOCUMENTERS)
        self.set_website(APP_URL)
        self.set_website_label('GitHub')
        self.show_all()
