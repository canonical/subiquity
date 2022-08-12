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
    UbuntuProSubscription,
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
    |      'pro attach' command.                              |
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
                          " 'pro attach' command."))


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
    subscription_done_label = _("Continue")

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
        | [ How to register -> ]                                  |
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
                _("How to register"),
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
        |      'pro attach' command.                              |
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

    def subscription_screen(self, subscription: UbuntuProSubscription) \
            -> Widget:
        """
        +---------------------------------------------------------+
        | Account Connected: user@domain.com                      |
        |             Token: C1NWcZTHLteJXGVMM6YhvHDpGrhyy7       |
        |      Subscription: Ubuntu Pro - Physical 24/5           |
        |                                                         |
        | List of your enabled services:                          |
        |                                                         |
        |   * ...                                                 |
        |   * ...                                                 |
        |                                                         |
        | Other available services:                               |
        |                                                         |
        |   * ...                                                 |
        |   * ...                                                 |
        |                                                         |
        | If you want to change the default enablements for your  |
        | token, you can do so via the ubuntu.com/pro web         |
        | interface. Alternatively, you can change enabled        |
        | services using the `pro' command-line tool once the     |
        | installation is finished.                               |
        |                                                         |
        |                       [ Continue ]                      |
        |                       [ Back     ]                      |
        +---------------------------------------------------------+
        """
        services = subscription.services
        auto_enabled = [svc for svc in services if svc.auto_enabled]
        can_be_enabled = [svc for svc in services if not svc.auto_enabled]

        rows: List[Widget] = []

        rows.extend([
            Text(_("Account Connected") + ": " + subscription.account_name),
            Text(_("            Token") + ": " + subscription.contract_token),
            Text(_("     Subscription") + ": " + subscription.contract_name),
        ])
        rows.append(Text(""))

        if auto_enabled:
            rows.append(Text(_("List of your enabled services:")))
            rows.append(Text(""))
            rows.extend(
                    [Text(f"  * {svc.description}") for svc in auto_enabled])

        if can_be_enabled:
            if auto_enabled:
                # available here means activable
                rows.append(Text(""))
                rows.append(Text(_("Other available services:")))
            else:
                rows.append(Text(_("Available services:")))
            rows.append(Text(""))
            rows.extend(
                    [Text(f"  * {svc.description}") for svc in can_be_enabled])

        def on_continue() -> None:
            self.controller.next_screen()

        def on_back() -> None:
            self._w = self.upgrade_yes_no_screen()

        back_button = back_btn(
                label=_("Back"),
                on_press=lambda unused: on_back())
        continue_button = done_btn(
                label=self.__class__.subscription_done_label,
                on_press=lambda unused: on_continue())

        widgets: List[Widget] = [
            Text(""),
            Pile(rows),
            Text(""),
            Text(_("If you want to change the default enablements for your"
                   " token, you can do so via the ubuntu.com/pro web"
                   " interface. Alternatively you can change enabled services"
                   " using the `pro` command-line tool once the installation"
                   " is finished.")),
            Text(""),
        ]

        return screen(
                ListBox(widgets),
                buttons=[continue_button, back_button],
                excerpt=None,
                focus_buttons=True)

    def upgrade_mode_done(self, form: UpgradeModeForm) -> None:
        """ Open the loading dialog and asynchronously check if the token is
        valid. """
        def on_success(subscription: UbuntuProSubscription) -> None:
            def show_subscription() -> None:
                self.remove_overlay()
                self.show_subscription(subscription=subscription)

            self.remove_overlay()
            widget = TokenAddedWidget(
                    parent=self,
                    on_continue=show_subscription)
            self.show_stretchy_overlay(widget)

        def on_failure(status: UbuntuProCheckTokenStatus) -> None:
            self.remove_overlay()
            token_field = form.with_contract_token_subform.widget.form.token
            if status == UbuntuProCheckTokenStatus.INVALID_TOKEN:
                self.show_invalid_token()
                token_field.in_error = True
                token_field.show_extra(("info_error", "Invalid token"))
                form.validated()
            elif status == UbuntuProCheckTokenStatus.EXPIRED_TOKEN:
                self.show_expired_token()
                token_field.in_error = True
                token_field.show_extra(("info_error", "Expired token"))
                form.validated()
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
        self.show_stretchy_overlay(InvalidTokenWidget(self))

    def show_expired_token(self) -> None:
        """ Display an overlay that indicates that the user-supplied token has
        expired. """
        self.show_stretchy_overlay(ExpiredTokenWidget(self))

    def show_unknown_error(self) -> None:
        """ Display an overlay that indicates that we were unable to retrieve
        the subscription information. Reasons can be multiple include lack of
        network connection, temporary service unavailability, API issue ...
        The user is prompted to continue anyway or go back.
        """
        self.show_stretchy_overlay(ContinueAnywayWidget(self))

    def show_subscription(self, subscription: UbuntuProSubscription) -> None:
        """ Display a screen with information about the subscription, including
        the list of services that can be enabled.  After the user confirms, we
        will quit the current view and move on. """
        self._w = self.subscription_screen(subscription=subscription)


class ExpiredTokenWidget(Stretchy):
    """ Widget that shows that the supplied token is expired.

    +--------------------- Expired token ---------------------+
    |                                                         |
    | Your token has expired. Please use another token to     |
    | continue.                                               |
    |                                                         |
    |                         [ Okay ]                        |
    +---------------------------------------------------------+
    """
    def __init__(self, parent: BaseView) -> None:
        """ Initializes the widget. """
        self.parent = parent
        cont = done_btn(label=_("Okay"), on_press=lambda unused: self.close())
        widgets = [
            Text(_("Your token has expired. Please use another token"
                   " to continue.")),
            Text(""),
            button_pile([cont]),
            ]
        super().__init__("Expired token", widgets,
                         stretchy_index=0, focus_index=2)

    def close(self) -> None:
        """ Close the overlay. """
        self.parent.remove_overlay()


class InvalidTokenWidget(Stretchy):
    """ Widget that shows that the supplied token is invalid.

    +--------------------- Invalid token ---------------------+
    |                                                         |
    | Your token could not be verified. Please ensure it is   |
    | correct and try again.                                  |
    |                                                         |
    |                         [ Okay ]                        |
    +---------------------------------------------------------+
    """
    def __init__(self, parent: BaseView) -> None:
        """ Initializes the widget. """
        self.parent = parent
        cont = done_btn(label=_("Okay"), on_press=lambda unused: self.close())
        widgets = [
            Text(_("Your token could not be verified. Please ensure it is"
                   " correct and try again.")),
            Text(""),
            button_pile([cont]),
            ]
        super().__init__("Invalid token", widgets,
                         stretchy_index=0, focus_index=2)

    def close(self) -> None:
        """ Close the overlay. """
        self.parent.remove_overlay()


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
    title = _("Token added successfully")
    done_label = _("Continue")

    def __init__(self, parent: UbuntuProView,
                 on_continue: Callable[[], None]) -> None:
        """ Initializes the widget. """
        self.parent = parent
        cont = done_btn(
                label=self.__class__.done_label,
                on_press=lambda unused: on_continue())
        widgets = [
            Text(_("Your token has been added successfully and your"
                   " subscription configuration will be applied at the first"
                   " boot.")),
            Text(""),
            button_pile([cont]),
            ]
        super().__init__(self.__class__.title, widgets,
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
    |_Create your Ubuntu One account with your email. Each    |
    | Ubuntu One account gets a free personal Ubuntu Pro      |
    | subscription for up to three machines, including        |
    | laptops, servers or cloud virtual machines.             |
    |                                                         |
    | Visit ubuntu.com/pro to get started.                    |
    |                                                         |
    |                       [ Continue ]                      |
    +---------------------------------------------------------+
    """
    def __init__(self, parent: UbuntuProView) -> None:
        """ Initializes the widget."""
        self.parent = parent

        ok = ok_btn(label=_("Continue"), on_press=lambda unused: self.close())

        title = _("How to register")
        header = _("Create your Ubuntu One account with your email. Each"
                   " Ubuntu One account gets a free personal Ubuntu Pro"
                   " subscription for up to three machines, including"
                   " laptops, servers or cloud virtual machines.")

        widgets: List[Widget] = [
            Text(header),
            Text(""),
            Text(_("Visit ubuntu.com/pro to get started.")),
            Text(""),
            button_pile([ok]),
        ]

        super().__init__(title, widgets, stretchy_index=2, focus_index=4)

    def close(self) -> None:
        """ Close the overlay. """
        self.parent.remove_overlay()


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
