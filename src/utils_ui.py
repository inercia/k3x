# utils_ui.py
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
from typing import Optional, Tuple, Callable

from gi.repository import GdkPixbuf, Granite, Gtk, Notify as notify

from .config import APP_TITLE
from .config import ApplicationSettings
from .utils import call_in_main_thread, running_on_main_thread


###############################################################################
# messages and notyfications
###############################################################################

def show_notification(msg, header: str = None, icon: str = None,
                      timeout: Optional[int] = None,
                      action: Optional[Tuple[str, Callable]] = None,
                      threaded: bool = True,
                      notification=None):
    """
    Show a desktop notification
    """
    # see https://lazka.github.io/pgi-docs/#Notify-0.7
    # maybe we could also use https://notify2.readthedocs.io/en/latest/

    if not header:
        header = APP_TITLE

    icon_filename = None
    if not icon:
        icon_filename = ApplicationSettings.get_app_icon()

    logging.info(msg)

    def do_notify(n=None):
        assert running_on_main_thread()

        # send the notification from the main thread
        if n is None:
            n = notify.Notification.new(header, msg, icon)
            n.set_app_name(APP_TITLE)

            if icon_filename:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_filename)
                n.set_icon_from_pixbuf(pixbuf)

            if timeout:
                # Note that the timeout may be ignored by the server.
                n.set_timeout(timeout)

            if action:
                action_str, action_callback = action
                r = random.randrange(0, 10000)
                n.add_action(f"{r}-{APP_TITLE}-id", action_str, action_callback, None)

            n.show()
        else:
            logging.debug("[UI] Updating notification")
            n.update(header, msg, icon)

        if not threaded:  # important: do not return anything if invoked with `call_in_main_thread`
            return n

    if threaded:
        call_in_main_thread(do_notify)
        return None
    else:
        return do_notify(notification)


def show_error_dialog(msg: str, explanation: str, icon: str = "dialog-error", ok_label: str = "Ok"):
    """
    Show a info/warning dialog, with just one OK button
    """
    error_diag = Granite.MessageDialog.with_image_from_icon_name(
        msg, "\n\n" + explanation, icon, Gtk.ButtonsType.OK_CANCEL)

    button_ok = Gtk.Button(label=ok_label)
    error_diag.add_action_widget(button_ok, Gtk.ResponseType.OK)

    error_diag.set_flags = Gtk.DialogFlags.MODAL

    error_diag.show_all()
    error_diag.run()
    error_diag.destroy()


def show_warning_dialog(msg: str, explanation: str):
    """
    Show a warning dialog, with just one OK button
    """
    show_error_dialog(msg, explanation, icon="dialog-warning")


def show_yes_no_dialog(msg: str, header: str, icon: str = "dialog-warning",
                       ok_label: str = "Ok", cancel_label: str = "Cancel",
                       window=None) -> str:
    delete_diag = Granite.MessageDialog.with_image_from_icon_name(header, "\n\n" + msg, icon, Gtk.ButtonsType.OK_CANCEL)

    button_delete = Gtk.Button(label=ok_label)
    button_delete.get_style_context().add_class(Gtk.STYLE_CLASS_DESTRUCTIVE_ACTION)
    delete_diag.add_action_widget(button_delete, Gtk.ResponseType.OK)

    button_cancel = Gtk.Button(label=cancel_label)
    button_cancel.get_style_context().add_class(Gtk.STYLE_CLASS_SUGGESTED_ACTION)
    delete_diag.add_action_widget(button_cancel, Gtk.ResponseType.CANCEL)

    if window:
        delete_diag.set_transient_for(window)

    delete_diag.set_flags = Gtk.DialogFlags.MODAL

    delete_diag.show_all()
    response = delete_diag.run()
    delete_diag.destroy()
    return response


###############################################################################
# settings
###############################################################################


def _link_gtk_entry_to_settings(settings, entry: Gtk.Entry, settings_id: str):
    """
    Link a Gtk.Entry to a GSettings ID, so any change in one of
    them will be reflected in the other one.
    """
    name = entry.get_name()
    logging.debug(f"[LINK] settings::{settings_id} <-> entry {name} [str]")
    curr_value = settings.get_safe_string(settings_id)
    if curr_value:
        entry.set_text(curr_value)

    settings.connect(f"changed::{settings_id}",
                     lambda s, k: entry.set_text(settings.get_safe_string(settings_id)))
    entry.connect("changed",
                  lambda e: settings.set_string(settings_id, str(entry.get_text())))


def _link_gtk_switch_to_settings(settings, switch: Gtk.Switch, settings_id: str):
    """
    Link a Gtk.Switch to a GSettings ID, so any change in one of
    them will be reflected in the other one.
    """
    name = switch.get_name()
    logging.debug(f"[LINK] settings::{settings_id} <-> switch {name} [bool]")
    curr_value = settings.get_boolean(settings_id)
    if curr_value:
        switch.set_state(curr_value)

    settings.connect(f"changed::{settings_id}",
                     lambda s, k: switch.set_state(settings.get_boolean(settings_id)))
    switch.connect("state-set",
                   lambda _sw, _state: settings.set_boolean(settings_id, _state))


def _link_gtk_spinbutton_to_settings(settings, spin: Gtk.SpinButton, settings_id: str):
    """
    Link a Gtk.SpinButton to a GSettings ID, so any change in one of
    them will be reflected in the other one.
    """
    name = spin.get_name()
    logging.debug(f"[LINK] settings::{settings_id} <-> spinbutton {name} [int]")
    curr_value = settings.get_int(settings_id)
    if curr_value:
        spin.set_value(settings.get_int(settings_id))

    settings.connect(f"changed::{settings_id}",
                     lambda s, k: spin.set_value(settings.get_int(settings_id)))
    spin.connect("change-value",
                 lambda e: settings.set_int(settings_id, spin.get_value()))


def _link_gtk_combobox_to_settings(settings, combo: Gtk.ComboBox, settings_id: str):
    def combo_changed(*args):
        tree_iter = combo.get_active_iter()
        if tree_iter is not None:
            model = combo.get_model()
            text = model[tree_iter][0]
        else:
            entry = combo.get_child()
            text = entry.get_text()
        settings.set_string(settings_id, text)

    def settings_changed(*args):
        value = settings.get_safe_string(settings_id)
        if value is None or value == "":
            combo.set_active(0)
        else:
            model = combo.get_model()
            for i in range(0, len(model)):
                text = model[i][0]
                if text == value:
                    combo.set_active(i)
                    return
            entry = combo.get_child()
            if hasattr(entry, "set_text"):
                entry.set_text(value)

    name = combo.get_name()
    logging.debug(f"[LINK] settings::{settings_id} <-> combo {name} [str]")
    settings_changed()
    settings.connect(f"changed::{settings_id}", lambda s, k: settings_changed)
    combo.connect("changed", combo_changed)


def link_widget_to_settings(settings, widget: Gtk.Widget, settings_id: str):
    """
    Link a Gtk.SpinButton to a GSettings ID, so any change in one of
    them will be reflected in the other one.
    """
    # note: take into account inheritance in these heuristics...
    if isinstance(widget, Gtk.ComboBox):
        _link_gtk_combobox_to_settings(settings, widget, settings_id)
    elif isinstance(widget, Gtk.SpinButton):
        _link_gtk_spinbutton_to_settings(settings, widget, settings_id)
    elif isinstance(widget, Gtk.Switch):
        _link_gtk_switch_to_settings(settings, widget, settings_id)
    elif isinstance(widget, Gtk.Entry):
        _link_gtk_entry_to_settings(settings, widget, settings_id)
    else:
        raise Exception("unsupported widget type to link")


###############################################################################
# settings UI
###############################################################################

class SettingsPage(Granite.SimpleSettingsPage):
    """
    A settings page, with some convenience functions.
    """

    # settings that will be reset when calling set_defaults()
    _managed_settings = []

    def __init__(self, settings, **kwargs):
        self._settings = settings
        super().__init__(**kwargs)

        self._entries = []
        self._entries_area = self.get_content_area()
        self._entries_area.set_halign(Gtk.Align.FILL)
        self._entries_area.set_hexpand(True)

    def append_entry(self, label, widget, setting=None):
        # attach to the grid (see https://python-gtk-3-tutorial.readthedocs.io/en/latest/layout.html#grid)
        count = len(self._entries)
        self._entries_area.attach(label, 0, count, 1, 1)
        self._entries_area.attach(widget, 1, count, 1, 1)
        self._entries.append(widget)
        if setting:
            link_widget_to_settings(self._settings, widget, setting)

    def append_labeled_entry(self, text, widget, setting=None):
        label = Gtk.Label(text)
        label.props.hexpand = False
        label.props.halign = Gtk.Align.END
        widget.props.halign = Gtk.Align.START
        self.append_entry(label, widget, setting=setting)

    def on_validate(self):
        """
        Validate all the settings, raising an exception if something is wrong
        """
        pass

    def on_apply(self):
        """
        Validate all the settings, raising an exception if something is wrong
        """
        pass

    def set_defaults(self):
        """
        Set all the settings to the default values.
        """
        for setting in self._managed_settings:
            logging.debug(f"[UI] Resetting {setting} to default value")
            self._settings.reset(setting)
