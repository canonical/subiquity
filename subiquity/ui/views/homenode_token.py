# Copyright 2024 Canonical, Ltd.
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

import logging
import re

from urwid import LineBox, Pile, Text, connect_signal

from subiquity.common.types import HomenodeTokenCheckStatus
from subiquitycore.ui.buttons import button_pile, cancel_btn, done_btn
from subiquitycore.ui.form import Form, simple_field
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.utils import Color, screen
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.homenode_token")

# Pattern for 5 words separated by dashes
TOKEN_PATTERN = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+$"


TokenField = simple_field(StringEditor)


class HomenodeTokenForm(Form):
    cancel_label = _("Back")
    ok_label = _("Continue")

    token = TokenField(
        _("Installation Key:"),
        help=_("Enter five words separated by dashes (e.g., word1-word2-word3-word4-word5)")
    )

    def validate_token(self):
        """Validate that the installation key is five words separated by dashes."""
        token = self.token.value
        if not token:
            return _("Installation key cannot be empty")
        
        if not re.match(TOKEN_PATTERN, token):
            return _("Installation key must be exactly five words separated by dashes (e.g., word1-word2-word3-word4-word5)")


class HomenodeTokenView(BaseView):
    title = _("Homenode Installation Key")

    def __init__(self, controller, token: str, has_network: bool):
        self.controller = controller
        self.has_network = has_network
        self.validation_status = None
        self.validation_message = None

        initial = {"token": token} if token else {}
        self.form = HomenodeTokenForm(initial=initial)

        connect_signal(self.form, "submit", self.done)
        connect_signal(self.form, "cancel", self.cancel)

        # Update excerpt based on network availability
        if has_network:
            excerpt = _("Enter your Homenode installation key consisting of five words separated by dashes.")
        else:
            excerpt = _(
                "Network is not available. Please configure network first to validate your installation key."
            )

        super().__init__(self.form.as_screen(excerpt=excerpt, focus_buttons=True))

    def done(self, result):
        log.debug("User input: %s", result.as_data())
        token = result.as_data()["token"]
        
        # If network is available, validate installation key before proceeding
        if self.has_network:
            self._validate_and_submit(token)
        else:
            # No network, just submit without validation
            self.controller.done(token)

    def _validate_and_submit(self, token: str):
        """Validate installation key via API and then submit if valid."""
        # Show checking overlay
        spinner = Spinner(style="dots", app=self.controller.app)
        spinner.start()
        checking_text = Text(_("Checking installation key..."))
        cancel_button = cancel_btn(
            label=_("Cancel"),
            on_press=lambda sender: self._cancel_validation()
        )
        
        overlay_widget = LineBox(
            Pile([
                ("pack", checking_text),
                ("pack", spinner),
                ("pack", button_pile([cancel_button])),
            ])
        )
        self.show_stretchy_overlay(overlay_widget)
        self.request_redraw_if_visible()

        def on_success():
            self.remove_overlay()
            self.controller.done(token)

        def on_failure(status, message):
            self.remove_overlay()
            self._show_validation_error(status, message)

        self.controller.check_token(token, on_success, on_failure)

    def _cancel_validation(self):
        """Cancel installation key validation."""
        self.controller.cancel_check_token()
        self.remove_overlay()

    def _show_validation_error(self, status: HomenodeTokenCheckStatus, message: str):
        """Show validation error message."""
        if status == HomenodeTokenCheckStatus.INVALID_TOKEN:
            error_msg = _("Invalid installation key. Please check and try again.")
        elif status == HomenodeTokenCheckStatus.EXPIRED_TOKEN:
            error_msg = _("Installation key has expired. Please use a valid key.")
        elif status == HomenodeTokenCheckStatus.NO_NETWORK:
            error_msg = _("Network is not available. Please configure network first.")
        else:
            error_msg = message or _("Failed to verify installation key. Please try again.")

        error_text = Color.info_error(Text(error_msg))
        ok_button = done_btn(
            label=_("OK"),
            on_press=lambda sender: self.remove_overlay()
        )
        
        overlay_widget = LineBox(
            Pile([
                ("pack", error_text),
                ("pack", button_pile([ok_button])),
            ])
        )
        self.show_stretchy_overlay(overlay_widget)
        self.request_redraw_if_visible()

    def cancel(self, result=None):
        self.controller.cancel()

