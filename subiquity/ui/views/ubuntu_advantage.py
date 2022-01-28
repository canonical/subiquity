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
from typing import List

from urwid import (
    connect_signal,
    LineBox,
    Text,
    Widget,
    )

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    done_btn,
    ok_btn,
    )
from subiquitycore.ui.container import (
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.form import (
    Form,
    simple_field,
    WantsToKnowFormField,
    )
from subiquitycore.ui.spinner import (
    Spinner,
    )
from subiquitycore.ui.stretchy import (
    Stretchy,
    )
from subiquitycore.ui.utils import (
    button_pile,
    SomethingFailed,
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


class CheckingUAToken(WidgetWrap):
    """ Widget displaying a loading animation while checking ubuntu advantage
    subscription. """
    def __init__(self, parent: BaseView):
        """ Initializes the loading animation widget. """
        self.parent = parent
        spinner = Spinner(parent.controller.app.aio_loop, style="dots")
        spinner.start()
        text = _("Checking Ubuntu Advantage subscription...")
        button = cancel_btn(label=_("Cancel"), on_press=self.cancel)
        self.width = len(text) + 4
        super().__init__(
            LineBox(
                Pile([
                    ('pack', Text(' ' + text)),
                    ('pack', spinner),
                    ('pack', button_pile([button])),
                    ])))

    def cancel(self, sender) -> None:
        """ Close the loading animation and cancel the check operation. """
        self.parent.controller.cancel_check_token()
        self.parent.remove_overlay()


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
        """ If no token was supplied, move on to the next screen.
        If a token was provided, open the loading dialog and
        asynchronously check if the token is valid. """
        log.debug("User input: %r", form.as_data())

        token: str = form.token.value
        if token:
            checking_token_overlay = CheckingUAToken(self)
            self.show_overlay(checking_token_overlay,
                              width=checking_token_overlay.width,
                              min_width=None)
            self.controller.check_token(token)
        else:
            self.controller.done(token)

    def cancel(self) -> None:
        """ Called when the user presses the Back button. """
        self.controller.cancel()

    def show_invalid_token(self) -> None:
        """ Display an overlay that indicates that the user-supplied token is
        invalid. """
        self.remove_overlay()
        self.show_stretchy_overlay(
                SomethingFailed(self,
                                "Invalid token.",
                                "The Ubuntu Advantage token that you provided"
                                " is invalid. Please make sure that you typed"
                                " your token correctly."))

    def show_expired_token(self) -> None:
        """ Display an overlay that indicates that the user-supplied token has
        expired. """
        self.remove_overlay()
        self.show_stretchy_overlay(
                SomethingFailed(self,
                                "Token expired.",
                                "The Ubuntu Advantage token that you provided"
                                " has expired. Please use a different token."))

    def show_unknown_error(self) -> None:
        """ Display an overlay that indicates that we were unable to retrieve
        the subscription information. Reasons can be multiple include lack of
        network connection, temporary service unavailability, API issue ...
        The user is prompted to continue anyway or go back.
        """
        self.remove_overlay()
        self.show_stretchy_overlay(ContinueAnywayWidget(self))

    def show_activable_services(self, services: List[dict]) -> None:
        """ Display an overlay with the list of services that can be enabled
        via Ubuntu Advantage subscription. After the user confirms, we will
        quit the current view and move on. """
        self.remove_overlay()
        self.show_stretchy_overlay(ShowServicesWidget(self, services))


class ShowServicesWidget(Stretchy):
    """ Widget to show the activable services for UA subscription. """
    def __init__(self, parent: UbuntuAdvantageView,
                 services: List[dict]) -> None:
        """ Initializes the widget by including the list of services as a
        bullet-point list. """
        self.parent = parent

        ok = ok_btn(label=_("OK"), on_press=self.ok)

        title = _("Activable Services")
        header = _("List of services that are activable through your "
                   "Ubuntu Advantage subscription:")

        widgets: List[Widget] = [
            Text(header),
            Text(""),
            Pile([Text(f"* {svc['description']}") for svc in services]),
            Text(""),
            Text("Once the installation has finished, you can enable these "
                 "services using the `ua` command-line tool."),
            Text(""),
            button_pile([ok]),
        ]

        super().__init__(title, widgets, 2, 6)

    def ok(self, sender) -> None:
        """ Close the overlay and submit the token. """
        self.parent.controller.done(self.parent.form.token.value)


class ContinueAnywayWidget(Stretchy):
    """ Widget that requests the user if he wants to go back or continue
    anyway. """
    def __init__(self, parent: UbuntuAdvantageView) -> None:
        """ Initializes the widget by showing two buttons, one to go back and
        one to move forward anyway. """
        self.parent = parent
        back = back_btn(label=_("Back"), on_press=self.back)
        cont = done_btn(label=_("Continue anyway"), on_press=self.cont)
        widgets = [
            Text("Unable to check your subscription information."
                 " Do you want to go back or continue anyway?"),
            Text(""),
            button_pile([back, cont]),
            ]
        super().__init__("Unknown error", widgets, 0, 2)

    def back(self, sender) -> None:
        """ Close the overlay. """
        self.parent.remove_overlay()

    def cont(self, sender) -> None:
        """ Move on to the next screen. """
        self.parent.controller.done(self.parent.form.token.value)
