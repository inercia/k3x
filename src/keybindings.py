# keybindings.py
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
from typing import Dict, Callable, List, Tuple

from .config import ApplicationSettings


def parse_keystroke(shortcut: str) -> List[str]:
    """
    Translates a keystroke description like "<Ctrl><Alt>P" in a list ["control", "alt", "p"]
    """
    res = []

    for sub in ["<Ctrl>", "<Ctr>", "<Control>", "Control", "<ctrl>", "<ctr>", "<control>", "control"]:
        if sub in shortcut:
            shortcut = shortcut.replace(sub, "")
            res += ["control"]
            break

    for sub in ["<Alt>", "<alt>", "Alt", "alt"]:
        if sub in shortcut:
            shortcut = shortcut.replace(sub, "")
            res += ["alt"]
            break

    for sub in ["<Shift>", "<shift>", "Shift", "shift"]:
        if sub in shortcut:
            shortcut = shortcut.replace(sub, "")
            res += ["shift"]
            break

    for sub in ["<Meta>", "<meta>", "Meta", "meta", "<Super>", "<super>", "Super", "super"]:
        if sub in shortcut:
            shortcut = shortcut.replace(sub, "")
            res += ["super"]
            break

    if len(shortcut) > 0:
        res += [shortcut.lower()]

    return res


class Keybindings(object):

    def __init__(self, settings: ApplicationSettings, mappings: Dict[str, Dict[str, Tuple[str, Callable]]]):
        """
        Creates keybindings for shortcuts stores in GSettings.
        The list of settings cannot be changed after created.

        Pass a map of (setting_id -> callback)
        """
        super().__init__()

        self._mappings = mappings
        self._settings = settings
        self._active_shortcuts = dict()

        # see https://github.com/timeyyy/system_hotkey
        from system_hotkey import SystemHotkey
        self._keybinder = SystemHotkey()
        self.rebind_all()

    def rebind_all(self):
        for category, shortcuts in self._mappings.items():

            if not shortcuts:
                continue

            for title, info in shortcuts.items():
                shortcut_id, callback = info
                shortcut = self._settings.get_keybinding(shortcut_id)

                parsed = parse_keystroke(shortcut)

                if not callback:
                    logging.warning(f"Empty callback for shortcut '{shortcut_id}': ignored")
                    continue

                if not shortcut:
                    logging.warning(f"Empty shortcut for settings '{shortcut_id}': ignored")
                    continue

                logging.info(f"Binding '{shortcut_id}' -> '{callback.__name__}'")

                if shortcut and shortcut in self._active_shortcuts and self._active_shortcuts[shortcut] != callback:
                    logging.debug(f"Removing current binding '{shortcut}'")
                    try:
                        self._keybinder.unregister(parsed)
                        del self._active_shortcuts[shortcut]
                    except Exception as e:
                        logging.error(f"Could not unbind '{shortcut}': {e}")
                        continue

                if shortcut and shortcut not in self._active_shortcuts:
                    logging.info(f"Binding '{shortcut}' ({parsed}) to '{callback.__name__}'")
                    try:
                        self._keybinder.register(parsed, callback=callback)
                        self._active_shortcuts[shortcut] = callback
                    except Exception as e:
                        logging.error(f"Could not bind {shortcut} to {callback.__name__}: {e}")
                        continue

                    self._settings.connect(f"changed::{shortcut_id}", lambda k, s: self.rebind_all())
