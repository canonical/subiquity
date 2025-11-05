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

from urwid import connect_signal

from subiquitycore.ui.form import Form, simple_field
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.utils import screen
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.homenode_token")

# Pattern for 5 words separated by dashes
TOKEN_PATTERN = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z0-9]+$"


TokenField = simple_field(StringEditor)


class HomenodeTokenForm(Form):
    cancel_label = _("Back")
    ok_label = _("Continue")

    token = TokenField(
        _("Token:"),
        help=_("Enter five words separated by dashes (e.g., word1-word2-word3-word4-word5)")
    )

    def validate_token(self):
        """Validate that the token is five words separated by dashes."""
        token = self.token.value
        if not token:
            return _("Token cannot be empty")
        
        if not re.match(TOKEN_PATTERN, token):
            return _("Token must be exactly five words separated by dashes (e.g., word1-word2-word3-word4-word5)")


class HomenodeTokenView(BaseView):
    title = _("Homenode Token")

    def __init__(self, controller, token):
        self.controller = controller

        initial = {"token": token} if token else {}
        self.form = HomenodeTokenForm(initial=initial)

        connect_signal(self.form, "submit", self.done)
        connect_signal(self.form, "cancel", self.cancel)

        excerpt = _("Enter your Homenode token consisting of five words separated by dashes.")

        super().__init__(self.form.as_screen(excerpt=excerpt, focus_buttons=True))

    def done(self, result):
        log.debug("User input: %s", result.as_data())
        token = result.as_data()["token"]
        self.controller.done(token)

    def cancel(self, result=None):
        self.controller.cancel()

