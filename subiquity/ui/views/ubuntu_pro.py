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

import asyncio
import logging
import re
from typing import Callable, List

from urwid import Columns, LineBox, Text, Widget, connect_signal

from subiquity.common.types import UbuntuProCheckTokenStatus, UbuntuProSubscription
from subiquitycore.ui.buttons import back_btn, cancel_btn, done_btn, menu_btn, ok_btn
from subiquitycore.ui.container import ListBox, Pile, WidgetWrap
from subiquitycore.ui.form import (
    NO_HELP,
    Form,
    RadioButtonField,
    ReadOnlyField,
    SubForm,
    SubFormField,
    WantsToKnowFormField,
    simple_field,
)
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import SomethingFailed, button_pile, screen
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.ubuntu_pro")


class ContractTokenEditor(StringEditor, WantsToKnowFormField):
    """Represent a text-box editor for the Ubuntu Pro Token."""

    def __init__(self):
        """Initialize the text-field editor for UA token."""
        self.valid_char_pat = r"[1-9A-HJ-NP-Za-km-z]"
        self.error_invalid_char = _("'{}' is not a valid character.")
        super().__init__()

    def valid_char(self, ch: str) -> bool:
        """Tells whether the character passed is within the range of allowed
        characters
        """
        if len(ch) == 1 and not re.match(self.valid_char_pat, ch):
            self.bff.in_error = True
            self.bff.show_extra(("info_error", self.error_invalid_char.format(ch)))
            return False
        return super().valid_char(ch)


class ContractTokenForm(SubForm):
    """Represents a sub-form requesting Ubuntu Pro token.
    +---------------------------------------------------------+
    |      Token: C123456789ABCDEF                            |
    |             From your admin, or from ubuntu.com/pro     |
    +---------------------------------------------------------+
    """

    ContractTokenField = simple_field(ContractTokenEditor)

    token = ContractTokenField(
        _("Token:"), help=_("From your admin, or from ubuntu.com/pro")
    )

    def validate_token(self):
        """Return an error if the token input does not match the expected
        format."""
        if not 24 <= len(self.token.value) <= 30:
            return _("Invalid token: should be between 24 and 30 characters")


class UbuntuOneForm(SubForm):
    """Represents a sub-form showing a user-code and requesting the user to
    browse ubuntu.com/pro/attach.
    +---------------------------------------------------------+
    |      Code: 1A3-4V6                                      |
    |            Attach machine via your Ubuntu One account   |
    +---------------------------------------------------------+
    """

    user_code = ReadOnlyField(
        _("Code:"), help=_("Attach machine via your Ubuntu One account")
    )


class UpgradeModeForm(Form):
    """Represents a form requesting information to enable Ubuntu Pro.
    +---------------------------------------------------------+
    | (X)  Enter code on ubuntu.com/pro/attach                |
    |      Code: 1A3-4V6                                      |
    |            Attach machine via your Ubuntu One account   |
    |                                                         |
    | ( )  Or add token manually                              |
    |      Token: C123456789ABCDEF                            |
    |             From your admin, or from ubuntu.com/pro     |
    |                                                         |
    |                       [ Waiting  ]                      |
    |                       [ Back     ]                      |
    +---------------------------------------------------------+
    """

    cancel_label = _("Back")
    ok_label = _("Continue")
    ok_label_waiting = _("Waiting")
    group: List[RadioButtonField] = []

    with_ubuntu_one = RadioButtonField(
        group, _("Enter code on ubuntu.com/pro/attach"), help=NO_HELP
    )
    with_ubuntu_one_subform = SubFormField(UbuntuOneForm, "", help=NO_HELP)

    with_contract_token = RadioButtonField(
        group, _("Or add token manually"), help=NO_HELP
    )
    with_contract_token_subform = SubFormField(ContractTokenForm, "", help=NO_HELP)

    def __init__(self, initial) -> None:
        """Initializer that configures the callback to run when the radios are
        checked/unchecked."""
        super().__init__(initial)
        connect_signal(
            self.with_contract_token.widget, "change", self._toggle_contract_token_input
        )
        connect_signal(
            self.with_ubuntu_one.widget, "change", self._toggle_ubuntu_one_input
        )

        if initial["with_contract_token_subform"]["token"]:
            self._toggle_contract_token_input(None, True)
            self._toggle_ubuntu_one_input(None, False)
        else:
            self._toggle_contract_token_input(None, False)
            self._toggle_ubuntu_one_input(None, True)

        # Make sure the OK button is disabled when we're using the user-code.
        self.with_ubuntu_one_subform.widget.form.user_code.in_error = True

    def _toggle_contract_token_input(self, sender, new_value):
        """Enable/disable the sub-form that requests the contract token."""
        self.with_contract_token_subform.enabled = new_value
        if new_value:
            self.buttons.base_widget[0].set_label(self.ok_label)

    def _toggle_ubuntu_one_input(self, sender, new_value):
        """Enable/disable the sub-form that shows the user-code."""
        self.with_ubuntu_one_subform.enabled = new_value
        if new_value:
            self.buttons.base_widget[0].set_label(self.ok_label_waiting)

    def set_user_code(self, user_code: str) -> None:
        """Show the new value of user code in a green backgroud."""
        value = ("user_code", user_code)

        self.with_ubuntu_one_subform.widget.form.user_code.value = value


class UpgradeYesNoForm(Form):
    """Represents a form asking if we want to upgrade to Ubuntu Pro.
    +---------------------------------------------------------+
    | (X)  Enable Ubuntu Pro                                  |
    |                                                         |
    | ( )  Skip for now                                       |
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

    upgrade = RadioButtonField(group, _("Enable Ubuntu Pro"), help=NO_HELP)
    skip = RadioButtonField(
        group,
        _("Skip for now"),
        help="\n"
        + _("You can always enable Ubuntu Pro later via the 'pro attach' command."),
    )


class UpgradeYesNoFormNoNetwork(UpgradeYesNoForm):
    """Represents a "read-only" form that does not let the user enable Ubuntu
    Pro because the network is unavailable.
    +---------------------------------------------------------+
    | ( )  Enable Ubuntu Pro                                  |
    |                                                         |
    | (X)  Skip Ubuntu Pro setup for now                      |
    |                                                         |
    |      Once you are connected to the Internet, you can    |
    |      enable Ubuntu Pro via the 'pro attach' command.    |
    |                                                         |
    |                       [ Continue ]                      |
    |                       [ Back     ]                      |
    +---------------------------------------------------------+
    """

    group: List[RadioButtonField] = []

    upgrade = RadioButtonField(group, _("Enable Ubuntu Pro"), help=NO_HELP)
    skip = RadioButtonField(
        group,
        _("Skip Ubuntu Pro setup for now"),
        help="\n"
        + _(
            "Once you are connected to the Internet, you can"
            " enable Ubuntu Po via the 'pro attach' command."
        ),
    )

    def __init__(self):
        """Initializer that disables the relevant fields."""
        super().__init__(initial={})
        self.upgrade.value = False
        self.upgrade.enabled = False
        self.skip.value = True


class CheckingContractToken(WidgetWrap):
    """Widget displaying a loading animation while checking ubuntu pro
    subscription."""

    def __init__(self, parent: BaseView):
        """Initializes the loading animation widget."""
        self.parent = parent
        spinner = Spinner(style="dots")
        spinner.start()
        text = _("Checking Ubuntu Pro subscription...")
        button = cancel_btn(label=_("Cancel"), on_press=self.cancel)
        self.width = len(text) + 4
        super().__init__(
            LineBox(
                Pile(
                    [
                        ("pack", Text(" " + text)),
                        ("pack", spinner),
                        ("pack", button_pile([button])),
                    ]
                )
            )
        )

    def cancel(self, sender) -> None:
        """Close the loading animation and cancel the check operation."""
        self.parent.controller.cancel_check_token()
        self.parent.remove_overlay()


class UbuntuProView(BaseView):
    """Represent the view of the Ubuntu Pro configuration."""

    title = _("Upgrade to Ubuntu Pro")
    subscription_done_label = _("Continue")

    def __init__(self, controller, token: str, has_network: bool):
        """Initialize the view with the default value for the token."""
        self.controller = controller

        self.has_network = has_network

        if self.has_network:
            self.upgrade_yes_no_form = UpgradeYesNoForm(
                initial={
                    "skip": not token,
                    "upgrade": bool(token),
                }
            )
        else:
            self.upgrade_yes_no_form = UpgradeYesNoFormNoNetwork()

        self.upgrade_mode_form = UpgradeModeForm(
            initial={
                "with_contract_token_subform": {"token": token},
                "with_contract_token": bool(token),
                "with_ubuntu_one": not token,
            }
        )

        def on_upgrade_yes_no_cancel(unused: UpgradeYesNoForm):
            """Function to call when hitting Done from the upgrade/skip
            screen."""
            self.cancel()

        def on_upgrade_mode_cancel(unused: UpgradeModeForm):
            """Function to call when hitting Back from the contract token
            form."""
            self._w = self.upgrade_yes_no_screen()

        connect_signal(self.upgrade_yes_no_form, "submit", self.upgrade_yes_no_done)
        connect_signal(self.upgrade_yes_no_form, "cancel", on_upgrade_yes_no_cancel)
        connect_signal(self.upgrade_mode_form, "submit", self.upgrade_mode_done)
        connect_signal(self.upgrade_mode_form, "cancel", on_upgrade_mode_cancel)

        # Throwaway tasks
        self.tasks: List[asyncio.Task] = []

        super().__init__(self.upgrade_yes_no_screen())

    def upgrade_mode_screen(self) -> Widget:
        """Return a screen that asks the user to provide a contract token or
        input a user-code on the portal.
        +---------------------------------------------------------+
        | To upgrade to Ubuntu Pro, use your existing free        |
        | personal, or company Ubuntu One account, or provide a   |
        | token.                                                  |
        |                                                         |
        | [ How to register -> ]                                  |
        |                                                         |
        | (X)  Enter code on ubuntu.com/pro/attach                |
        |      Code: 1A3-4V6                                      |
        |            Attach machine via your Ubuntu One account   |
        |                                                         |
        | ( )  Or add token manually                              |
        |      Token: C123456789ABCDEF                            |
        |             From your admin, or from ubuntu.com/pro     |
        |                                                         |
        |                        [ Continue ]                     |
        |                        [ Back     ]                     |
        +---------------------------------------------------------+
        """

        excerpt = _(
            "To upgrade to Ubuntu Pro, use your existing free"
            " personal, or company Ubuntu One account, or provide a"
            " token."
        )

        how_to_register_btn = menu_btn(
            _("How to register"), on_press=lambda unused: self.show_how_to_register()
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
            focus_buttons=True,
        )

    def upgrade_yes_no_screen(self) -> Widget:
        """Return a screen that asks the user to skip or upgrade.
        +---------------------------------------------------------+
        | Upgrade this machine to Ubuntu Pro for security updates |
        | on a much wider range of packages, until 2032. Assists  |
        | with FedRAMP, FIPS, STIG, HIPAA and other compliance or |
        | hardening requirements.                                 |
        |                                                         |
        | [ About Ubuntu Pro -> ]                                 |
        |                                                         |
        | ( )  Enable Ubuntu Pro                                  |
        |                                                         |
        | (X)  Skip for now                                       |
        |      You can always enable Ubuntu Pro later via the     |
        |      'pro attach' command.                              |
        |                                                         |
        |                        [ Continue ]                     |
        |                        [ Back     ]                     |
        +---------------------------------------------------------+
        """
        security_updates_until = 2032

        excerpt = _(
            "Upgrade this machine to Ubuntu Pro for security updates"
            " on a much wider range of packages, until"
            f" {security_updates_until}. Assists with FedRAMP, FIPS,"
            " STIG, HIPAA and other compliance or hardening"
            " requirements."
        )
        excerpt_no_net = _("An Internet connection is required to enable Ubuntu Pro.")

        about_pro_btn = menu_btn(
            _("About Ubuntu Pro"), on_press=lambda unused: self.show_about_ubuntu_pro()
        )

        bp = button_pile([about_pro_btn])
        bp.align = "left"
        rows = [
            bp,
            Text(""),
        ] + self.upgrade_yes_no_form.as_rows()
        return screen(
            ListBox(rows),
            self.upgrade_yes_no_form.buttons,
            excerpt=excerpt if self.has_network else excerpt_no_net,
            focus_buttons=True,
        )

    def subscription_screen(self, subscription: UbuntuProSubscription) -> Widget:
        """
        +---------------------------------------------------------+
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

        rows.extend(
            [
                Text(_("Subscription") + ": " + subscription.contract_name),
            ]
        )
        rows.append(Text(""))

        if auto_enabled:
            rows.append(Text(_("List of your enabled services:")))
            rows.append(Text(""))
            rows.extend([Text(f"  * {svc.description}") for svc in auto_enabled])

        if can_be_enabled:
            if auto_enabled:
                # available here means activable
                rows.append(Text(""))
                rows.append(Text(_("Other available services:")))
            else:
                rows.append(Text(_("Available services:")))
            rows.append(Text(""))
            rows.extend([Text(f"  * {svc.description}") for svc in can_be_enabled])

        def on_continue() -> None:
            self.controller.next_screen()

        def on_back() -> None:
            self._w = self.upgrade_yes_no_screen()

        back_button = back_btn(label=_("Back"), on_press=lambda unused: on_back())
        continue_button = done_btn(
            label=self.__class__.subscription_done_label,
            on_press=lambda unused: on_continue(),
        )

        widgets: List[Widget] = [
            Text(""),
            Pile(rows),
            Text(""),
            Text(
                _(
                    "If you want to change the default enablements for your"
                    " token, you can do so via the ubuntu.com/pro web"
                    " interface. Alternatively you can change enabled services"
                    " using the `pro` command-line tool once the installation"
                    " is finished."
                )
            ),
            Text(""),
        ]

        return screen(
            ListBox(widgets),
            buttons=[continue_button, back_button],
            excerpt=None,
            focus_buttons=True,
        )

    def contract_token_check_ok(self, subscription: UbuntuProSubscription) -> None:
        """Close the "checking-token" overlay and open the token added overlay
        instead."""

        def show_subscription() -> None:
            self.remove_overlay()
            self.show_subscription(subscription=subscription)

        self.remove_overlay()
        widget = TokenAddedWidget(parent=self, on_continue=show_subscription)
        self.show_stretchy_overlay(widget)

    def upgrade_mode_done(self, form: UpgradeModeForm) -> None:
        """Open the loading dialog and asynchronously check if the token is
        valid."""

        def on_success(subscription: UbuntuProSubscription) -> None:
            def noop() -> None:
                pass

            if self.controller.cs_initiated:
                self.controller.contract_selection_cancel(on_cancelled=noop)
            self.contract_token_check_ok(subscription)

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
        self.show_overlay(
            checking_token_overlay, width=checking_token_overlay.width, min_width=None
        )

        self.controller.check_token(token, on_success=on_success, on_failure=on_failure)

    def cs_initiated(self, user_code: str) -> None:
        """Function to call when the contract selection has successfully
        initiated. It will start the polling asynchronously."""

        def reinitiate() -> None:
            self.controller.contract_selection_initiate(on_initiated=self.cs_initiated)

        self.upgrade_mode_form.set_user_code(user_code)
        self.controller.contract_selection_wait(
            on_contract_selected=self.on_contract_selected,
            on_timeout=reinitiate,
        )

    def on_contract_selected(self, contract_token: str) -> None:
        """Function to call when the contract selection has finished
        succesfully."""
        checking_token_overlay = CheckingContractToken(self)
        self.show_overlay(
            checking_token_overlay, width=checking_token_overlay.width, min_width=None
        )

        def on_failure(status: UbuntuProCheckTokenStatus) -> None:
            """Open a message box stating that the contract-token
            obtained via contract-selection is not valid ; and then go
            back to the previous screen."""

            log.error(
                "contract-token obtained via contract-selection"
                " counld not be validated: %r",
                status,
            )
            self._w = self.upgrade_mode_screen()
            self.show_stretchy_overlay(
                SomethingFailed(
                    self,
                    msg=_("Internal error"),
                    stderr=_("Could not add the contract token selected."),
                )
            )

        # It would be uncommon to have this call fail in production
        # because the contract token obtained via contract-selection is
        # expected to be valid. During testing, a mismatch in the
        # environment used (e.g., staging in subiquity and production
        # in u-a-c) can lead to this error though.
        self.controller.check_token(
            contract_token,
            on_success=self.contract_token_check_ok,
            on_failure=on_failure,
        )

    def upgrade_yes_no_done(self, form: UpgradeYesNoForm) -> None:
        """If skip is selected, move on to the next screen.
        Otherwise, show the form requesting a contract token."""
        if form.skip.value:
            self.controller.done("")
        else:

            def initiate() -> None:
                self.controller.contract_selection_initiate(
                    on_initiated=self.cs_initiated
                )

            self._w = self.upgrade_mode_screen()
            if self.controller.cs_initiated:
                # Cancel the existing contract selection before initiating a
                # new one.
                self.controller.contract_selection_cancel(on_cancelled=initiate)
            else:
                initiate()

    def cancel(self) -> None:
        """Called when the user presses the Back button."""
        self.controller.cancel()

    def show_about_ubuntu_pro(self) -> None:
        """Display an overlay that shows information about Ubuntu Pro."""
        self.show_stretchy_overlay(AboutProWidget(self))

    def show_how_to_register(self) -> None:
        """Display an overlay that shows instructions to register to
        Ubuntu Pro."""
        self.show_stretchy_overlay(HowToRegisterWidget(self))

    def show_invalid_token(self) -> None:
        """Display an overlay that indicates that the user-supplied token is
        invalid."""
        self.show_stretchy_overlay(InvalidTokenWidget(self))

    def show_expired_token(self) -> None:
        """Display an overlay that indicates that the user-supplied token has
        expired."""
        self.show_stretchy_overlay(ExpiredTokenWidget(self))

    def show_unknown_error(self) -> None:
        """Display an overlay that indicates that we were unable to retrieve
        the subscription information. Reasons can be multiple include lack of
        network connection, temporary service unavailability, API issue ...
        The user is prompted to continue anyway or go back.
        """
        question = _(
            "Unable to check your subscription information."
            " Do you want to go back or continue anyway?"
        )

        async def confirm_continue_anyway() -> None:
            confirmed = await self.ask_confirmation(
                title=_("Unknown error"),
                question=question,
                cancel_label=_("Back"),
                confirm_label=_("Continue anyway"),
            )

            if confirmed:
                subform = self.upgrade_mode_form.with_contract_token_subform
                self.controller.done(subform.value["token"])

        self.tasks.append(asyncio.create_task(confirm_continue_anyway()))

    def show_subscription(self, subscription: UbuntuProSubscription) -> None:
        """Display a screen with information about the subscription, including
        the list of services that can be enabled.  After the user confirms, we
        will quit the current view and move on."""
        self._w = self.subscription_screen(subscription=subscription)


class ExpiredTokenWidget(Stretchy):
    """Widget that shows that the supplied token is expired.

    +--------------------- Expired token ---------------------+
    |                                                         |
    | Your token has expired. Please use another token to     |
    | continue.                                               |
    |                                                         |
    |                         [ Okay ]                        |
    +---------------------------------------------------------+
    """

    def __init__(self, parent: BaseView) -> None:
        """Initializes the widget."""
        self.parent = parent
        cont = done_btn(label=_("Okay"), on_press=lambda unused: self.close())
        widgets = [
            Text(_("Your token has expired. Please use another token to continue.")),
            Text(""),
            button_pile([cont]),
        ]
        super().__init__("Expired token", widgets, stretchy_index=0, focus_index=2)

    def close(self) -> None:
        """Close the overlay."""
        self.parent.remove_overlay()


class InvalidTokenWidget(Stretchy):
    """Widget that shows that the supplied token is invalid.

    +--------------------- Invalid token ---------------------+
    |                                                         |
    | Your token could not be verified. Please ensure it is   |
    | correct and try again.                                  |
    |                                                         |
    |                         [ Okay ]                        |
    +---------------------------------------------------------+
    """

    def __init__(self, parent: BaseView) -> None:
        """Initializes the widget."""
        self.parent = parent
        cont = done_btn(label=_("Okay"), on_press=lambda unused: self.close())
        widgets = [
            Text(
                _(
                    "Your token could not be verified. Please ensure it is"
                    " correct and try again."
                )
            ),
            Text(""),
            button_pile([cont]),
        ]
        super().__init__("Invalid token", widgets, stretchy_index=0, focus_index=2)

    def close(self) -> None:
        """Close the overlay."""
        self.parent.remove_overlay()


class TokenAddedWidget(Stretchy):
    """Widget that shows that the supplied token is valid and was "added".
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

    def __init__(self, parent: UbuntuProView, on_continue: Callable[[], None]) -> None:
        """Initializes the widget."""
        self.parent = parent
        cont = done_btn(
            label=self.__class__.done_label, on_press=lambda unused: on_continue()
        )
        widgets = [
            Text(
                _(
                    "Your token has been added successfully and your"
                    " subscription configuration will be applied at the first"
                    " boot."
                )
            ),
            Text(""),
            button_pile([cont]),
        ]
        super().__init__(self.__class__.title, widgets, stretchy_index=0, focus_index=2)


class AboutProWidget(Stretchy):
    """Widget showing some information about what Ubuntu Pro offers.
    +------------------- About Ubuntu Pro --------------------+
    |                                                         |
    | Ubuntu Pro is the same base Ubuntu, with an additional  |
    | layer of security and compliance services and security  |
    | patches covering a wider range of packages.             |
    |   • Security patch coverage for CVSS critical, high and |
    |     selected medium vulnerabilities in all 23,000       |
    |     packages in "universe" (extended from the normal    |
    |     2,300 "main" packages).                             |
    |   • ...                                                 |
    |   • ...                                                 |
    |                                                         |
    | Ubuntu Pro is free for personal use on up to 3 machines.|
    | More information is at ubuntu.com/pro                   |
    |                                                         |
    |                       [ Continue ]                      |
    +---------------------------------------------------------+
    """

    def __init__(self, parent: UbuntuProView) -> None:
        """Initializes the widget."""
        self.parent = parent

        ok = ok_btn(label=_("Continue"), on_press=lambda unused: self.close())

        title = _("About Ubuntu Pro")
        header = _(
            "Ubuntu Pro is the same base Ubuntu, with an additional"
            " layer of security and compliance services and security"
            " patches covering a wider range of packages."
        )

        universe_packages = 23000
        main_packages = 2300

        services = [
            _(
                "Security patch coverage for CVSS critical, high and selected"
                f" medium vulnerabilities in all {universe_packages:,} packages"
                f' in "universe" (extended from the normal {main_packages:,}'
                ' "main" packages).'
            ),
            _("10 years of security patch coverage (extended from 5 years)."),
            _("Kernel Livepatch to reduce required reboots."),
            _("Ubuntu Security Guide for CIS and DISA-STIG hardening."),
            _("FIPS 140-2 NIST-certified crypto-modules for FedRAMP compliance"),
        ]

        def itemize(item: str, marker: str = "•") -> Columns:
            """Return the text specified in a Text widget prepended with a
            bullet point / marker. If the text is too long to fit in a single
            line, the continuation lines are indented as shown below:
            +---------------------------+
            | * This is an example of   |
            |   what such element would |
            |   look like.              |
            +---------------------------+
            """
            return Columns([(len(marker), Text(marker)), Text(item)], dividechars=1)

        widgets: List[Widget] = [
            Text(header),
            Text(""),
            Pile([itemize(svc, marker="  •") for svc in services]),
            Text(""),
            Text(_("Ubuntu Pro is free for personal use on up to 3 machines.")),
            Text(_("More information is at ubuntu.com/pro")),
            Text(""),
            button_pile([ok]),
        ]

        super().__init__(title, widgets, stretchy_index=2, focus_index=7)

    def close(self) -> None:
        """Close the overlay."""
        self.parent.remove_overlay()


class HowToRegisterWidget(Stretchy):
    """Widget showing some instructions to register to Ubuntu Pro.
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
        """Initializes the widget."""
        self.parent = parent

        ok = ok_btn(label=_("Continue"), on_press=lambda unused: self.close())

        title = _("How to register")
        header = _(
            "Create your Ubuntu One account with your email. Each"
            " Ubuntu One account gets a free personal Ubuntu Pro"
            " subscription for up to three machines, including"
            " laptops, servers or cloud virtual machines."
        )

        widgets: List[Widget] = [
            Text(header),
            Text(""),
            Text(_("Visit ubuntu.com/pro to get started.")),
            Text(""),
            button_pile([ok]),
        ]

        super().__init__(title, widgets, stretchy_index=2, focus_index=4)

    def close(self) -> None:
        """Close the overlay."""
        self.parent.remove_overlay()
