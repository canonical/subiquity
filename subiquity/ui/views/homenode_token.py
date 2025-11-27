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

from urwid import Text, connect_signal

from subiquity.common.types import HomenodeTokenCheckStatus
from subiquitycore.ui.buttons import cancel_btn, done_btn
from subiquitycore.ui.form import Form, simple_field
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import Color, button_pile, screen
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.homenode_token")

# Pattern for 5 words separated by dashes
TOKEN_PATTERN = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+$"


TokenField = simple_field(StringEditor)


class CheckingTokenStretchy(Stretchy):
    """Overlay that shows a spinner while checking the installation key."""
    
    def __init__(self, parent, on_cancel):
        self.parent = parent
        self.on_cancel = on_cancel
        
        spinner = Spinner(style="dots", app=parent.controller.app)
        spinner.start()
        
        widgets = [
            Text(_("Checking installation key...")),
            spinner,
            Text(""),
            button_pile([cancel_btn(label=_("Cancel"), on_press=self._cancel)]),
        ]
        super().__init__(_("Validating"), widgets, 0, 0)
    
    def _cancel(self, sender=None):
        self.on_cancel()


class TokenValidationErrorStretchy(Stretchy):
    """Overlay that shows an error message when token validation fails."""
    
    def __init__(self, parent, error_msg):
        self.parent = parent
        
        widgets = [
            Color.info_error(Text(error_msg)),
            Text(""),
            button_pile([done_btn(label=_("OK"), on_press=self._close)]),
        ]
        super().__init__(_("Validation Error"), widgets, 0, 2)
    
    def _close(self, sender=None):
        self.parent.remove_overlay()


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
        
        log.info("HomenodeTokenView.done called with has_network=%s", self.has_network)
        log.info("Token value: %s (length: %d)", token[:20] + "..." if len(token) > 20 else token, len(token))
        
        # Always try to validate if network might be available
        # The API endpoint will check network status again
        log.info("Attempting to validate installation key via API")
        self._validate_and_submit(token)

    def _validate_and_submit(self, token: str):
        """Validate installation key via API and then submit if valid."""
        log.info("_validate_and_submit called for token: %s", token[:10] + "..." if len(token) > 10 else token)
        log.info("View has_network flag: %s", self.has_network)
        
        # Disable the form button to prevent multiple submissions
        self.form.done_btn.enabled = False
        self.form.validated()
        
        # Show checking overlay
        self.show_stretchy_overlay(CheckingTokenStretchy(self, self._cancel_validation))
        self.request_redraw_if_visible()
        log.info("Overlay shown, calling check_token")

        def on_success():
            log.info("Token validation successful, proceeding to next screen")
            self.remove_overlay()
            # Only proceed if validation succeeded
            self.controller.done(token)

        def on_failure(status, message):
            log.warning("Token validation failed: status=%s, message=%s", status, message)
            self.remove_overlay()
            # Re-enable the form button so user can try again
            self.form.done_btn.enabled = True
            self.form.validated()
            self._show_validation_error(status, message)

        log.info("About to call controller.check_token with token length: %d", len(token))
        try:
            self.controller.check_token(token, on_success, on_failure)
            log.info("controller.check_token called successfully")
        except Exception as e:
            log.exception("Exception calling controller.check_token: %s", e)
            self.remove_overlay()
            self.form.done_btn.enabled = True
            self.form.validated()
            self._show_validation_error(
                HomenodeTokenCheckStatus.UNKNOWN_ERROR,
                f"Failed to start validation: {str(e)}"
            )

    def _cancel_validation(self):
        """Cancel installation key validation."""
        self.controller.cancel_check_token()
        self.remove_overlay()
        # Re-enable the form button
        self.form.done_btn.enabled = True
        self.form.validated()

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

        self.show_stretchy_overlay(TokenValidationErrorStretchy(self, error_msg))
        self.request_redraw_if_visible()

    def cancel(self, result=None):
        self.controller.cancel()

