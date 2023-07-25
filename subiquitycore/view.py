# Copyright 2015 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

""" View policy

Contains some default key navigations
"""

import asyncio
import logging

from urwid import Overlay, Text, emit_signal

from subiquitycore.ui.confirmation import ConfirmationOverlay
from subiquitycore.ui.container import Columns, Pile, WidgetWrap
from subiquitycore.ui.stretchy import StretchyOverlay
from subiquitycore.ui.utils import disabled, undisabled

log = logging.getLogger("subiquitycore.view")


class OverlayNotFoundError(Exception):
    """Exception to raise when trying to remove a non-existent overlay."""


class BaseView(WidgetWrap):
    def local_help(self):
        """Help for what the user is currently looking at.

        Returns title, documentation (or None, None).
        """
        return None, None

    def show_overlay(self, overlay_widget, **kw):
        args = dict(
            align="center",
            width=("relative", 60),
            min_width=80,
            valign="middle",
            height="pack",
        )
        PADDING = 3
        # Don't expect callers to account for the padding if
        # they pass a fixed width.
        if "width" in kw:
            if isinstance(kw["width"], int):
                kw["width"] += 2 * PADDING
        args.update(kw)
        top = Pile(
            [
                ("pack", Text("")),
                Columns([(PADDING, Text("")), overlay_widget, (PADDING, Text(""))]),
                ("pack", Text("")),
            ]
        )
        self._w = Overlay(top_w=top, bottom_w=disabled(self._w), **args)

    def show_stretchy_overlay(self, stretchy):
        emit_signal(stretchy, "opened")
        stretchy.opened()
        self._w = StretchyOverlay(disabled(self._w), stretchy)

    async def ask_confirmation(
        self, title: str, question: str, confirm_label: str, cancel_label: str
    ) -> bool:
        """Open a confirmation dialog using a strechy overlay.
        If the user selects the "yes" button, the function returns True.
        If the user selects the "no" button or closes the dialog, the function
        returns False.
        """
        confirm_queue = asyncio.Queue(maxsize=1)

        def on_confirm():
            confirm_queue.put_nowait(True)

        def on_cancel():
            confirm_queue.put_nowait(False)

        stretchy = ConfirmationOverlay(
            title=title,
            question=question,
            confirm_label=confirm_label,
            cancel_label=cancel_label,
            on_confirm=on_confirm,
            on_cancel=on_cancel,
        )

        self.show_stretchy_overlay(stretchy)

        confirmed = await confirm_queue.get()
        # The callback might have been called as the result of the overlay
        # getting closed (when ESC is pressed). Therefore, the overlay may or
        # may not still be opened.
        self.remove_overlay(stretchy, not_found_ok=True)

        return confirmed

    def remove_overlay(self, stretchy=None, *, not_found_ok=False) -> None:
        """Remove (frontmost) overlay from the view."""
        if stretchy is not None:
            one_above = None
            cur = self._w
            while isinstance(cur, (StretchyOverlay, Overlay)):
                cur_stretchy = getattr(cur, "stretchy", None)
                if cur_stretchy is stretchy:
                    emit_signal(stretchy, "closed")
                    stretchy.closed()
                    if one_above is not None:
                        one_above.bottom_w = cur.bottom_w
                    else:
                        self._w = undisabled(cur.bottom_w)
                    return
                one_above = cur
                cur = undisabled(cur.bottom_w)
            else:
                if not not_found_ok:
                    raise OverlayNotFoundError
        else:
            try:
                behind_overlay = self._w.bottom_w
            except AttributeError:
                if not_found_ok:
                    return
                raise OverlayNotFoundError

            if isinstance(self._w, StretchyOverlay):
                emit_signal(self._w.stretchy, "closed")
                self._w.stretchy.closed()
            self._w = undisabled(behind_overlay)

    def cancel(self):
        pass

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == "esc":
            try:
                self.remove_overlay(not_found_ok=False)
            except OverlayNotFoundError:
                self.cancel()
                return None
        return key
