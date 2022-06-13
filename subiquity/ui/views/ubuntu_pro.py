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
from typing import Callable, List

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


class ContractTokenEditor(StringEditor, WantsToKnowFormField):
    """ Represent a text-box editor for the Ubuntu Pro Token.  """
    def __init__(self):
        """ Initialize the text-field editor for UA token. """
        self.valid_char_pat = r"[1-9A-HJ-NP-Za-km-z]"
        self.error_invalid_char = _("'{}' is not a valid character.")
        super().__init__()

    def valid_char(self, ch: str) -> bool:
        """ Tells whether the character passed is within the range of allowed
        characters
        """
        if len(ch) == 1 and not re.match(self.valid_char_pat, ch):
            self.bff.in_error = True
            self.bff.show_extra(
                    ("info_error", self.error_invalid_char.format(ch)))
            return False
        return super().valid_char(ch)


class ContractTokenForm(SubForm):
    """ Represents a sub-form requesting Ubuntu Pro token.
    +---------------------------------------------------------+
    |      Token: C123456789ABCDEF                            |
    |             This is your Ubuntu Pro token               |
    +---------------------------------------------------------+
    """
    ContractTokenField = simple_field(ContractTokenEditor)

    token = ContractTokenField(
            _("Token:"),
            help=_("This is your Ubuntu Pro token"))

    def validate_token(self):
        """ Return an error if the token input does not match the expected
        format. """
        if not 24 <= len(self.token.value) <= 30:
            return _("Invalid token: should be between 24 and 30 characters")


class UpgradeModeForm(Form):
    """ Represents a form requesting the Ubuntu Pro credentials.
    +---------------------------------------------------------+
    | (X)  Add token manually                                 |
    |      Token: C123456789ABCDEF                            |
    |             This is your Ubuntu Pro token               |
    |                                                         |
    |                       [ Continue ]                      |
    |                       [ Back     ]                      |
    +---------------------------------------------------------+
    """
    cancel_label = _("Back")
    ok_label = _("Continue")
    group: List[RadioButtonField] = []

    with_contract_token = RadioButtonField(
            group, _("Add token manually"),
            help=NO_HELP)
    with_contract_token_subform = SubFormField(
            ContractTokenForm, "", help=NO_HELP)

    def __init__(self, initial) -> None:
        """ Initializer that configures the callback to run when the radio is
        checked/unchecked. Since there is a single radio for now, it can
        only be unchecked programmatically. """
        super().__init__(initial)
        connect_signal(self.with_contract_token.widget,
                       'change', self._toggle_contract_token_input)

    def _toggle_contract_token_input(self, sender, new_value):
        """ Enable/disable the sub-form that requests the contract token. """
        self.with_contract_token_subform.enabled = new_value


class UpgradeYesNoForm(Form):
    """ Represents a form asking if we want to upgrade to Ubuntu Pro.
    +---------------------------------------------------------+
    | (X)  Upgrade to Ubuntu Pro                              |
    |                                                         |
    | ( )  Do this later                                      |
    |                                                         |
    |      You can always enable Ubuntu Pro later via the     |
    |      'ua attach' command                                |
    |                                                         |
    |                       [ Continue ]                      |
    |                       [ Back     ]                      |
    +---------------------------------------------------------+
    """

    cancel_label = _("Back")
    ok_label = _("Continue")
    group: List[RadioButtonField] = []

    upgrade = RadioButtonField(
            group, _("Upgrade to Ubuntu Pro"),
            help=NO_HELP)
    skip = RadioButtonField(
            group, _("Do this later"),
            help="\n" + _("You can always enable Ubuntu Pro later via the"
                          " 'ua attach' command."))


class CheckingContractToken(WidgetWrap):
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
    """ Represent the view of the Ubuntu Pro configuration. """

    title = _("Upgrade to Ubuntu Pro")

    def __init__(self, controller, token: str):
        """ Initialize the view with the default value for the token. """
        self.controller = controller

        self.upgrade_yes_no_form = UpgradeYesNoForm(initial={
            "skip": not token,
            "upgrade": bool(token),
            })
        self.upgrade_mode_form = UpgradeModeForm(initial={
            "with_contract_token_subform": {"token": token},
            })

        def on_upgrade_yes_no_cancel(unused: UpgradeYesNoForm):
            """ Function to call when hitting Done from the upgrade/skip
            screen. """
            self.cancel()

        def on_upgrade_mode_cancel(unused: UpgradeModeForm):
            """ Function to call when hitting Back from the contract token
            form. """
            self._w = self.upgrade_yes_no_screen()

        connect_signal(self.upgrade_yes_no_form,
                       'submit', self.upgrade_yes_no_done)
        connect_signal(self.upgrade_yes_no_form,
                       'cancel', on_upgrade_yes_no_cancel)
        connect_signal(self.upgrade_mode_form,
                       'submit', self.upgrade_mode_done)
        connect_signal(self.upgrade_mode_form,
                       'cancel', on_upgrade_mode_cancel)

        super().__init__(self.upgrade_yes_no_screen())

    def upgrade_mode_screen(self) -> Widget:
        """ Return a screen that asks the user for his information (e.g.,
        contract token).
        +---------------------------------------------------------+
        | To upgrade to Ubuntu Pro, you can enter your token      |
        | manually.                                               |
        |                                                         |
        | [ How to Register -> ]                                  |
        |                                                         |
        | (X)  Add token manually                                 |
        |      Token: C123456789ABCDEF                            |
        |             This is your Ubuntu Pro token               |
        |                                                         |
        |                        [ Continue ]                     |
        |                        [ Back     ]                     |
        +---------------------------------------------------------+
        """

        excerpt = _("To upgrade to Ubuntu Pro, you can enter your token"
                    " manually.")

        how_to_register_btn = menu_btn(
                _("How to Register"),
                on_press=lambda unused: self.show_how_to_register()
                )
        bp = button_pile([how_to_register_btn])
        bp.align = "left"
        rows = [
            bp,
            Text(""),
        ] + self.upgrade_mode_form.as_rows()
        return screen(
                ListBox(rows),
                self.upgrade_mode_form.buttons,
                excerpt=excerpt,
                focus_buttons=True)

    def upgrade_yes_no_screen(self) -> Widget:
        """ Return a screen that asks the user to skip or upgrade.
        +---------------------------------------------------------+
        | Upgrade this machine to Ubuntu Pro or skip this step.   |
        |                                                         |
        | [ About Ubuntu Pro -> ]                                 |
        |                                                         |
        | ( )  Upgrade to Ubuntu Pro                              |
        |                                                         |
        | (X)  Do this later                                      |
        |      You can always enable Ubuntu Pro later via the     |
        |      'ua attach' command.                               |
        |                                                         |
        |                        [ Continue ]                     |
        |                        [ Back     ]                     |
        +---------------------------------------------------------+
        """

        excerpt = _("Upgrade this machine to Ubuntu Pro or skip this step.")

        about_pro_btn = menu_btn(
                _("About Ubuntu Pro"),
                on_press=lambda unused: self.show_about_ubuntu_pro())

        bp = button_pile([about_pro_btn])
        bp.align = "left"
        rows = [
            bp,
            Text(""),
        ] + self.upgrade_yes_no_form.as_rows()
        return screen(
                ListBox(rows),
                self.upgrade_yes_no_form.buttons,
                excerpt=excerpt,
                focus_buttons=True)

    def upgrade_mode_done(self, form: UpgradeModeForm) -> None:
        """ Open the loading dialog and asynchronously check if the token is
        valid. """
        def on_success(services: List[UbuntuProService]) -> None:
            def show_services() -> None:
                self.remove_overlay()
                self.show_activable_services(services)

            self.remove_overlay()
            widget = TokenAddedWidget(
                    parent=self,
                    on_continue=show_services)
            self.show_stretchy_overlay(widget)

        def on_failure(status: UbuntuProCheckTokenStatus) -> None:
            self.remove_overlay()
            if status == UbuntuProCheckTokenStatus.INVALID_TOKEN:
                self.show_invalid_token()
            elif status == UbuntuProCheckTokenStatus.EXPIRED_TOKEN:
                self.show_expired_token()
            elif status == UbuntuProCheckTokenStatus.UNKNOWN_ERROR:
                self.show_unknown_error()

        token: str = form.with_contract_token_subform.value["token"]
        checking_token_overlay = CheckingContractToken(self)
        self.show_overlay(checking_token_overlay,
                          width=checking_token_overlay.width,
                          min_width=None)

        self.controller.check_token(token,
                                    on_success=on_success,
                                    on_failure=on_failure)

    def upgrade_yes_no_done(self, form: UpgradeYesNoForm) -> None:
        """ If skip is selected, move on to the next screen.
        Otherwise, show the form requesting the contract token. """
        if form.skip.value:
            self.controller.done("")
        else:
            self._w = self.upgrade_mode_screen()

    def cancel(self) -> None:
        """ Called when the user presses the Back button. """
        self.controller.cancel()

    def show_about_ubuntu_pro(self) -> None:
        """ Display an overlay that shows information about Ubuntu Pro. """
        self.show_stretchy_overlay(AboutProWidget(self))

    def show_how_to_register(self) -> None:
        """ Display an overlay that shows instructions to register to
        Ubuntu Pro. """
        self.show_stretchy_overlay(HowToRegisterWidget(self))

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
        # TODO: replace this by a full screen.
        # Changing the text in the title bar is what makes it difficult.
        self.show_stretchy_overlay(ShowServicesWidget(self, services))


class TokenAddedWidget(Stretchy):
    """ Widget that shows that the supplied token is valid and was "added".
    +---------------- Token added successfully ---------------+
    |                                                         |
    | Your token has been added successfully and your         |
    | subscription configuration will be applied at the first |
    | boot.                                                   |
    |                                                         |
    |                       [ Continue ]                      |
    +---------------------------------------------------------+
    """
    def __init__(self, parent: UbuntuProView,
                 on_continue: Callable[[], None]) -> None:
        """ Initializes the widget. """
        self.parent = parent
        cont = done_btn(
                label=_("Continue"),
                on_press=lambda unused: on_continue())
        widgets = [
            Text(_("Your token has been added successfully and your"
                   " subscription configuration will be applied at the first"
                   " boot.")),
            Text(""),
            button_pile([cont]),
            ]
        super().__init__("Token added successfully", widgets,
                         stretchy_index=0, focus_index=2)


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


class HowToRegisterWidget(Stretchy):
    """ Widget showing some instructions to register to Ubuntu Pro.
    +-------------------- How to register --------------------+
    |                                                         |
    | You can register for a free Ubuntu One account and get  |
    | a personal token for up to 3 machines.                  |
    |                                                         |
    | To register an account, visit ubuntu.com/pro on another |
    | device.                                                 |
    |                                                         |
    |                       [ Continue ]                      |
    +---------------------------------------------------------+
    """
    def __init__(self, parent: UbuntuProView) -> None:
        """ Initializes the widget."""
        self.parent = parent

        ok = ok_btn(label=_("Continue"), on_press=lambda unused: self.close())

        title = _("How to register")
        header = _("You can register for a free Ubuntu One account and get a"
                   " personal token for up to 3 machines.")

        widgets: List[Widget] = [
            Text(header),
            Text(""),
            Text("To register an account, visit ubuntu.com/pro on another"
                 " device."),
            Text(""),
            button_pile([ok]),
        ]

        super().__init__(title, widgets, stretchy_index=2, focus_index=4)

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
        subform = self.parent.upgrade_mode_form.with_contract_token_subform
        self.parent.controller.done(subform.value["token"])


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
        subform = self.parent.upgrade_mode_form.with_contract_token_subform
        self.parent.controller.done(subform.value["token"])
