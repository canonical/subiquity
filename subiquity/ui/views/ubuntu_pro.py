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
""" Module that defines the view class for Ubuntu Pro configuration. """

import logging
import re
from typing import List

from urwid import (
    Columns,
    connect_signal,
    LineBox,
    Text,
    Widget,
    )

from subiquity.common.types import (
    UbuntuProCheckTokenStatus,
    UbuntuProService,
    )
from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    done_btn,
    menu_btn,
    ok_btn,
    )
from subiquitycore.ui.container import (
    ListBox,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.form import (
    Form,
    SubForm,
    SubFormField,
    NO_HELP,
    simple_field,
    RadioButtonField,
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
    screen,
    SomethingFailed,
    )

from subiquitycore.ui.interactive import StringEditor


log = logging.getLogger('subiquity.ui.views.ubuntu_pro')


class UATokenEditor(StringEditor, WantsToKnowFormField):
    """ Represent a text-box editor for the Ubuntu Pro Token.  """
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


class UbuntuProTokenForm(SubForm):
    """ Represents a sub-form requesting Ubuntu Pro token.
    +---------------------------------------------------------+
    |      Token: C123456789ABCDEF                            |
    |             This is your Ubuntu Pro token               |
    +---------------------------------------------------------+
    """
    UATokenField = simple_field(UATokenEditor)

    token = UATokenField(_("Token:"),
                         help=_("This is your Ubuntu Pro token"))


class UbuntuProForm(Form):
    """
    Represents a form requesting Ubuntu Pro information
    +---------------------------------------------------------+
    | (X)  Enable now with my contract token                  |
    |                                                         |
    |      Token: C123456789ABCDEF                            |
    |             This is your Ubuntu Pro token               |
    |                                                         |
    | ( )  Skip Ubuntu Pro for now                            |
    |                                                         |
    |      You can always enable Ubuntu Pro later via the     |
    |      'ua attach' command.                               |
    |                                                         |
    |                         [ Done ]                        |
    |                         [ Back ]                        |
    +---------------------------------------------------------+
    """
    cancel_label = _("Back")
    group = []

    with_token = RadioButtonField(
            group,
            _("Enable now with my contract token"), help=NO_HELP)
    token_form = SubFormField(UbuntuProTokenForm, "", help=NO_HELP)
    skip_ua = RadioButtonField(
            group, _("Do this later"),
            help="\n" + _("You can always enable Ubuntu Pro later via the"
                          " 'ua attach' command."))

    def __init__(self, initial):
        super().__init__(initial)
        connect_signal(self.with_token.widget,
                       'change', self._toggle_token_input)

        if not initial["token_form"]["token"]:
            self.skip_ua.widget.state = True
            self.with_token.widget.state = False
        else:
            self.skip_ua.widget.state = False
            self.with_token.widget.state = True

    def _toggle_token_input(self, sender, new_value):
        self.token_form.enabled = new_value


class CheckingUAToken(WidgetWrap):
    """ Widget displaying a loading animation while checking ubuntu pro
    subscription. """
    def __init__(self, parent: BaseView):
        """ Initializes the loading animation widget. """
        self.parent = parent
        spinner = Spinner(parent.controller.app.aio_loop, style="dots")
        spinner.start()
        text = _("Checking Ubuntu Pro subscription...")
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


class UbuntuProView(BaseView):
    """ Represent the view of the Ubuntu Pro configuration.
    +---------------------------------------------------------+
    | Enable Ubuntu Pro                              [ Help ] |
    +---------------------------------------------------------+
    | If you want to enable Ubuntu Pro, you can do it now     |
    | with your contract token. Otherwise, you can skip this  |
    | step and enable Ubuntu Pro later using the command      |
    | 'ua attach'.                                            |
    |                                                         |
    | (X)  Enable now with my contract token                  |
    |                                                         |
    |      Token: C123456789ABCDEF                            |
    |             This is your Ubuntu Pro token               |
    |                                                         |
    | ( )  Skip Ubuntu Pro for now                            |
    |                                                         |
    |                         [ Done ]                        |
    |                         [ Back ]                        |
    +---------------------------------------------------------+
    """

    title = _("Upgrade to Ubuntu Pro")
    excerpt = _("If you want to upgrade to Ubuntu Pro, you can do it now with"
                " your contract token. "
                "Otherwise, you can skip this step.")

    def __init__(self, controller, token: str):
        """ Initialize the view with the default value for the token. """
        self.controller = controller

        self.form = UbuntuProForm(initial={"token_form": {"token": token}})

        def on_cancel(_: UbuntuProForm):
            self.cancel()

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', on_cancel)

        about_pro_btn = menu_btn(
                _("About Ubuntu Pro"),
                on_press=lambda unused: self.show_about_ubuntu_pro())

        bp = button_pile([about_pro_btn])
        bp.align = "left"
        rows = [
            bp,
            Text(""),
        ] + self.form.as_rows()
        super().__init__(
            screen(
                ListBox(rows),
                self.form.buttons,
                excerpt=self.excerpt,
                focus_buttons=True))

    def done(self, form: UbuntuProForm) -> None:
        """ If no token was supplied, move on to the next screen.
        If a token was provided, open the loading dialog and
        asynchronously check if the token is valid. """
        results = form.as_data()
        if not results["skip_ua"]:
            def on_success(services: List[UbuntuProService]) -> None:
                self.remove_overlay()
                self.show_activable_services(services)

            def on_failure(status: UbuntuProCheckTokenStatus) -> None:
                self.remove_overlay()
                if status == UbuntuProCheckTokenStatus.INVALID_TOKEN:
                    self.show_invalid_token()
                elif status == UbuntuProCheckTokenStatus.EXPIRED_TOKEN:
                    self.show_expired_token()
                elif status == UbuntuProCheckTokenStatus.UNKNOWN_ERROR:
                    self.show_unknown_error()

            token: str = results["token_form"]["token"]
            checking_token_overlay = CheckingUAToken(self)
            self.show_overlay(checking_token_overlay,
                              width=checking_token_overlay.width,
                              min_width=None)

            self.controller.check_token(token,
                                        on_success=on_success,
                                        on_failure=on_failure)
        else:
            self.controller.done("")

    def cancel(self) -> None:
        """ Called when the user presses the Back button. """
        self.controller.cancel()

    def show_about_ubuntu_pro(self) -> None:
        """ Display an overlay that shows information about Ubuntu Pro. """
        self.show_stretchy_overlay(AboutProWidget(self))

    def show_invalid_token(self) -> None:
        """ Display an overlay that indicates that the user-supplied token is
        invalid. """
        self.show_stretchy_overlay(
                SomethingFailed(self,
                                "Invalid token.",
                                "The Ubuntu Pro token that you provided"
                                " is invalid. Please make sure that you typed"
                                " your token correctly."))

    def show_expired_token(self) -> None:
        """ Display an overlay that indicates that the user-supplied token has
        expired. """
        self.show_stretchy_overlay(
                SomethingFailed(self,
                                "Token expired.",
                                "The Ubuntu Pro token that you provided"
                                " has expired. Please use a different token."))

    def show_unknown_error(self) -> None:
        """ Display an overlay that indicates that we were unable to retrieve
        the subscription information. Reasons can be multiple include lack of
        network connection, temporary service unavailability, API issue ...
        The user is prompted to continue anyway or go back.
        """
        self.show_stretchy_overlay(ContinueAnywayWidget(self))

    def show_activable_services(self,
                                services: List[UbuntuProService]) -> None:
        """ Display an overlay with the list of services that can be enabled
        via Ubuntu Pro subscription. After the user confirms, we will
        quit the current view and move on. """
        self.show_stretchy_overlay(ShowServicesWidget(self, services))


class AboutProWidget(Stretchy):
    """ Widget showing some information about what Ubuntu Pro offers.
    +------------------- About Ubuntu Pro --------------------+
    |                                                         |
    | Ubuntu Pro subscription gives you access to multiple    |
    | security & compliance services, including:              |
    |                                                         |
    | • Security patching for over 30.000 packages, with a    |
    |   focus on High and Critical CVEs (extended from 2.500) |
    | • ...                                                   |
    | • ...                                                   |
    |                                                         |
    | Ubuntu Pro is free for personal use on up to 3 machines.|
    | More information on ubuntu.com/pro                      |
    |                                                         |
    |                       [ Continue ]                      |
    +---------------------------------------------------------+
    """
    def __init__(self, parent: UbuntuProView) -> None:
        """ Initializes the widget."""
        self.parent = parent

        ok = ok_btn(label=_("Continue"), on_press=lambda unused: self.close())

        title = _("About Ubuntu Pro")
        header = _("Ubuntu Pro subscription gives you access to multiple"
                   " security & compliance services, including:")

        services = [
            _("Security patching for over 30.000 packages, with a focus on"
              " High and Critical CVEs (extended from 2.500)"),
            _("10 years of security Maintenance (extended from 5 years)"),
            _("Kernel Livepatch service for increased uptime and security"),
            _("Ubuntu Security Guide for hardening profiles, including CIS"
              " and DISA-STIG"),
            _("FIPS 140-2 NIST-certified crypto-modules for FedRAMP"
              " compliance"),
        ]

        def itemize(item: str, marker: str = "•") -> Columns:
            """ Return the text specified in a Text widget prepended with a
            bullet point / marker. If the text is too long to fit in a single
            line, the continuation lines are indented as shown below:
            +---------------------------+
            | * This is an example of   |
            |   what such element would |
            |   look like.              |
            +---------------------------+
            """
            return Columns(
                    [(len(marker), Text(marker)), Text(item)], dividechars=1)

        widgets: List[Widget] = [
            Text(header),
            Text(""),
            Pile([itemize(svc) for svc in services]),
            Text(""),
            Text(_("Ubuntu Pro is free for personal use on up to 3"
                   " machines.")),
            Text(_("More information on ubuntu.com/pro")),
            Text(""),
            button_pile([ok]),
        ]

        super().__init__(title, widgets, stretchy_index=2, focus_index=7)

    def close(self) -> None:
        """ Close the overlay. """
        self.parent.remove_overlay()


class ShowServicesWidget(Stretchy):
    """ Widget to show the activable services for UA subscription.
    +------------------ Activable Services -------------------+
    |                                                         |
    | List of services that are activable through your Ubuntu |
    | Pro subscription:                                       |
    | * ...                                                   |
    | * ...                                                   |
    |                                                         |
    | One the installation has finished, you can enable these |
    | services using the 'ua' command-line tool.              |
    |                                                         |
    |                          [ OK ]                         |
    +---------------------------------------------------------+
    """
    def __init__(self, parent: UbuntuProView,
                 services: List[UbuntuProService]) -> None:
        """ Initializes the widget by including the list of services as a
        bullet-point list. """
        self.parent = parent

        ok = ok_btn(label=_("OK"), on_press=self.ok)

        title = _("Activable Services")
        header = _("List of services that are activable through your "
                   "Ubuntu Pro subscription:")

        widgets: List[Widget] = [
            Text(header),
            Text(""),
            Pile([Text(f"* {svc.description}") for svc in services]),
            Text(""),
            Text("Once the installation has finished, you can enable these "
                 "services using the `ua` command-line tool."),
            Text(""),
            button_pile([ok]),
        ]

        super().__init__(title, widgets, 2, 6)

    def ok(self, sender) -> None:
        """ Close the overlay and submit the token. """
        token = self.parent.form.as_data()["token_form"]["token"]
        self.parent.controller.done(token)


class ContinueAnywayWidget(Stretchy):
    """ Widget that requests the user if he wants to go back or continue
    anyway.
    +--------------------- Unknown error ---------------------+
    |                                                         |
    | Unable to check your subscription information. Do you   |
    | want to go back or continue anyway?                     |
    |                                                         |
    |                   [ Back            ]                   |
    |                   [ Continue anyway ]                   |
    +---------------------------------------------------------+
    """
    def __init__(self, parent: UbuntuProView) -> None:
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
        token = self.parent.form.as_data()["token_form"]["token"]
        self.parent.controller.done(token)
