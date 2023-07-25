# Copyright 2023 Canonical, Ltd.
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

from typing import Callable

import urwid

from subiquitycore.ui.buttons import back_btn, done_btn
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import button_pile


class ConfirmationOverlay(Stretchy):
    """An overlay widget that asks the user to confirm or cancel an action."""

    def __init__(
        self,
        title: str,
        question: str,
        confirm_label: str,
        cancel_label: str,
        on_confirm: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self.on_cancel_cb = on_cancel
        self.on_confirm_cb = on_confirm
        self.choice_made = False

        widgets = [
            urwid.Text(question),
            urwid.Text(""),
            button_pile(
                [
                    back_btn(label=cancel_label, on_press=lambda u: self.on_cancel()),
                    done_btn(label=confirm_label, on_press=lambda u: self.on_confirm()),
                ]
            ),
        ]

        super().__init__(title, widgets, 0, 2)

    def on_cancel(self) -> None:
        self.choice_made = True
        self.on_cancel_cb()

    def on_confirm(self) -> None:
        self.choice_made = True
        self.on_confirm_cb()

    def closed(self):
        if self.choice_made:
            return
        # The caller should be careful not to close the overlay again.
        self.on_cancel_cb()
