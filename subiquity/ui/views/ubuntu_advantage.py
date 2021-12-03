# Copyright 2021 Canonical, Ltd.
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
""" Module that defines the view class for Ubuntu Advantage configuration. """

import logging
import re

from urwid import connect_signal

from subiquitycore.view import BaseView
from subiquitycore.ui.form import (
    Form,
    simple_field,
    WantsToKnowFormField,
)

from subiquitycore.ui.interactive import StringEditor


log = logging.getLogger('subiquity.ui.views.ubuntu_advantage')

ua_help = _("If you want to enroll this system using your Ubuntu Advantage "
            "subscription, enter your Ubuntu Advantage token here. "
            "Otherwise, leave this blank.")


class UATokenEditor(StringEditor, WantsToKnowFormField):
    """ Represent a text-box editor for the Ubuntu Advantage Token.  """
    def __init__(self):
        """ Initialize the text-field editor for UA token. """
        self.valid_char_pat = r"[a-zA-Z0-9]"
        self.error_invalid_char = _("The only characters permitted in this "
                                    "field are alphanumeric characters.")
        super().__init__()

    def valid_char(self, ch: str) -> bool:
        """ Tells whether the character passed is within the range of allowed
        characters
        """
        if len(ch) == 1 and not re.match(self.valid_char_pat, ch):
            self.bff.in_error = True
            self.bff.show_extra(("info_error", self.error_invalid_char))
            return False
        return super().valid_char(ch)


class UbuntuAdvantageForm(Form):
    """
    Represents a form requesting Ubuntu Advantage information
    """
    cancel_label = _("Back")

    UATokenField = simple_field(UATokenEditor)

    token = UATokenField(_("Ubuntu Advantage token:"), help=ua_help)


class UbuntuAdvantageView(BaseView):
    """ Represent the view of the Ubuntu Advantage configuration. """

    title = _("Enable Ubuntu Advantage")
    excerpt = _("Enter your Ubuntu Advantage token if you want to enroll "
                "this system.")

    def __init__(self, controller, token: str):
        """ Initialize the view with the default value for the token. """
        self.controller = controller

        self.form = UbuntuAdvantageForm(initial={"token": token})

        def on_cancel(_: UbuntuAdvantageForm):
            self.cancel()

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', on_cancel)

        super().__init__(self.form.as_screen(excerpt=_(self.excerpt)))

    def done(self, form: UbuntuAdvantageForm) -> None:
        """ Called when the user presses the Done button. """
        log.debug("User input: %r", form.as_data())

        self.controller.done(form.token.value)

    def cancel(self) -> None:
        """ Called when the user presses the Back button. """
        self.controller.cancel()
