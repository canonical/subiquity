# Copyright 2018 Canonical, Ltd.
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
from typing import List

from urwid import LineBox, Text, connect_signal

from subiquity.common.types import SSHData, SSHIdentity
from subiquity.ui.views.identity import UsernameField
from subiquitycore.ui.actionmenu import Action, ActionMenu
from subiquitycore.ui.buttons import cancel_btn, done_btn, menu_btn, ok_btn
from subiquitycore.ui.container import ListBox, Pile, WidgetWrap
from subiquitycore.ui.form import BooleanField, ChoiceField, Form, Toggleable
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import ColSpec, TablePile, TableRow
from subiquitycore.ui.utils import (
    Color,
    Padding,
    SomethingFailed,
    button_pile,
    make_action_menu_row,
    screen,
)
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.ssh")


SSH_IMPORT_MAXLEN = 256 + 3  # account for lp: or gh:
IMPORT_KEY_LABEL = _("Import SSH key")

_ssh_import_data = {
    "gh": {
        "caption": _("GitHub Username:"),
        "help": _("Enter your GitHub username."),
        "valid_char": r"[a-zA-Z0-9\-]",
        "error_invalid_char": _(
            "A GitHub username may only contain alphanumeric characters or hyphens."
        ),
    },
    "lp": {
        "caption": _("Launchpad Username:"),
        "help": "Enter your Launchpad username.",
        "valid_char": r"[a-z0-9\+\.\-]",
        "error_invalid_char": _(
            "A Launchpad username may only contain "
            "lower-case alphanumeric characters, hyphens, "
            "plus, or periods."
        ),
    },
}


class SSHImportForm(Form):
    service = ChoiceField(
        _("Import SSH identity:"),
        choices=[
            (_("from GitHub"), True, "gh"),
            (_("from Launchpad"), True, "lp"),
        ],
        help=_("You can import your SSH keys from GitHub or Launchpad."),
    )

    import_username = UsernameField(_ssh_import_data["gh"]["caption"])

    # validation of the import username does not read from
    # service.value because it is sometimes done from the
    # 'select' signal of the service selector, which is called
    # before the service selector's value has actually changed. so
    # the signal handler stuffs the value here before doing
    # validation (yes, this is a hack).
    service_value = None

    def validate_import_username(self):
        username = self.import_username.value
        if len(username) == 0:
            return _("This field must not be blank.")
        if len(username) > SSH_IMPORT_MAXLEN:
            return _("SSH id too long, must be < ") + str(SSH_IMPORT_MAXLEN)
        if self.service_value == "lp":
            lp_regex = r"^[a-z0-9][a-z0-9\+\.\-]*$"
            if not re.match(lp_regex, self.import_username.value):
                return _(
                    "A Launchpad username must start with a letter or "
                    "number. All letters must be lower-case. The "
                    "characters +, - and . are also allowed after "
                    "the first character."
                    ""
                )
        elif self.service_value == "gh":
            if not re.match(r"^[a-zA-Z0-9\-]+$", username):
                return _(
                    "A GitHub username may only contain alphanumeric "
                    "characters or single hyphens, and cannot begin or "
                    "end with a hyphen."
                )


class SSHImportStretchy(Stretchy):
    def __init__(self, parent):
        self.parent = parent
        self.form = SSHImportForm(initial={})

        connect_signal(self.form, "submit", lambda unused: self.done())
        connect_signal(self.form, "cancel", lambda unused: self.cancel())
        connect_signal(
            self.form.service.widget, "select", self._import_service_selected
        )

        self._import_service_selected(
            sender=None, service=self.form.service.widget.value
        )

        rows = self.form.as_rows()
        title = _("Import SSH key")
        super().__init__(title, [Pile(rows), Text(""), self.form.buttons], 0, 0)

    def cancel(self):
        self.parent.remove_overlay(self)

    def done(self):
        ssh_import_id = self.form.service.value + ":" + self.form.import_username.value
        fsk = FetchingSSHKeys(self.parent)
        self.parent.remove_overlay(self)
        self.parent.show_overlay(fsk, width=fsk.width, min_width=None)
        self.parent.controller.fetch_ssh_keys(ssh_import_id=ssh_import_id)

    def _import_service_selected(self, sender, service: str):
        iu = self.form.import_username
        data = _ssh_import_data[service]
        iu.help = _(data["help"])
        iu.caption = _(data["caption"])
        iu.widget.valid_char_pat = data["valid_char"]
        iu.widget.error_invalid_char = _(data["error_invalid_char"])
        self.form.service_value = service
        if iu.value != "":
            iu.validate()


class SSHShowKeyStretchy(Stretchy):
    def __init__(self, parent, key: str) -> None:
        self.parent = parent
        widgets = [
            Text(key),
            Text(""),
            button_pile([done_btn(_("Close"), on_press=self.close)]),
        ]

        title = _("SSH key")
        super().__init__(title, widgets, 0, 2)

    def close(self, button=None) -> None:
        self.parent.remove_overlay()


class SSHForm(Form):
    install_server = BooleanField(_("Install OpenSSH server"))

    pwauth = BooleanField(_("Allow password authentication over SSH"))

    cancel_label = _("Back")


class FetchingSSHKeys(WidgetWrap):
    def __init__(self, parent):
        self.parent = parent
        self.spinner = Spinner(style="dots", app=self.parent.controller.app)
        self.spinner.start()
        text = _("Fetching SSH keys...")
        button = cancel_btn(label=_("Cancel"), on_press=self.cancel)
        # | text |
        # 12    34
        self.width = len(text) + 4
        super().__init__(
            LineBox(
                Pile(
                    [
                        ("pack", Text(" " + text)),
                        ("pack", self.spinner),
                        ("pack", button_pile([button])),
                    ]
                )
            )
        )

    def cancel(self, sender):
        self.spinner.stop()
        self.parent.remove_overlay()
        self.parent.controller._fetch_cancel()


class ConfirmSSHKeys(Stretchy):
    def __init__(self, parent, identities: List[SSHIdentity]):
        self.parent = parent
        self.identities: List[SSHIdentity] = identities

        ok = ok_btn(label=_("Yes"), on_press=self.ok)
        cancel = cancel_btn(label=_("No"), on_press=self.cancel)

        if len(identities) > 1:
            title = _("Confirm SSH keys")
            header = _(
                "Keys with the following fingerprints were fetched. "
                "Do you want to use them?"
            )
        else:
            title = _("Confirm SSH key")
            header = _(
                "A key with the following fingerprint was fetched. "
                "Do you want to use it?"
            )

        fingerprints = Pile([Text(identity.key_fingerprint) for identity in identities])

        super().__init__(
            title,
            [
                Text(header),
                Text(""),
                fingerprints,
                Text(""),
                button_pile([ok, cancel]),
            ],
            2,
            4,
        )

    def cancel(self, sender):
        self.parent.remove_overlay()

    def ok(self, sender):
        for identity in self.identities:
            self.parent.add_key_to_table(identity.to_authorized_key())
        self.parent.refresh_keys_table()

        self.parent.remove_overlay()


class SSHView(BaseView):
    title = _("SSH configuration")
    excerpt = _(
        "You can choose to install the OpenSSH server package to "
        "enable secure remote access to your server."
    )

    def __init__(self, controller, ssh_data):
        self.controller = controller

        initial = {
            "install_server": ssh_data.install_server,
            "pwauth": ssh_data.allow_pw,
        }

        self.form = SSHForm(initial=initial)
        self.keys = ssh_data.authorized_keys

        self._import_key_btn = Toggleable(
            menu_btn(
                label=IMPORT_KEY_LABEL,
                on_press=lambda unused: self.show_import_key_overlay(),
            )
        )
        bp = button_pile([self._import_key_btn])
        bp.align = "left"

        colspecs = {
            0: ColSpec(rpad=1),
            1: ColSpec(can_shrink=True),
            2: ColSpec(rpad=1),
            3: ColSpec(rpad=1),
        }
        self.keys_table = TablePile([], colspecs=colspecs)
        self.refresh_keys_table()

        rows = self.form.as_rows() + [
            Text(""),
            bp,
            Text(""),
            Text(_("AUTHORIZED KEYS")),
            Text(""),
            self.keys_table,
        ]

        connect_signal(self.form, "submit", self.done)
        connect_signal(self.form, "cancel", self.cancel)
        connect_signal(self.form.install_server.widget, "change", self._toggle_server)

        self._toggle_server(None, self.form.install_server.value)

        super().__init__(
            screen(
                ListBox(rows),
                self.form.buttons,
                excerpt=_(self.excerpt),
                focus_buttons=False,
            )
        )

    def done(self, sender):
        log.debug("User input: {}".format(self.form.as_data()))
        ssh_data = SSHData(
            install_server=self.form.install_server.value,
            allow_pw=self.form.pwauth.value,
            authorized_keys=self.keys,
        )

        self.controller.done(ssh_data)

    def cancel(self, result=None):
        self.controller.cancel()

    def show_import_key_overlay(self):
        self.show_stretchy_overlay(SSHImportStretchy(self))

    def confirm_ssh_keys(self, ssh_import_id, identities: List[SSHIdentity]):
        self.remove_overlay()
        self.show_stretchy_overlay(ConfirmSSHKeys(self, identities))

    def fetching_ssh_keys_failed(self, msg, stderr):
        self.remove_overlay()
        self.show_stretchy_overlay(SomethingFailed(self, msg, stderr))

    def add_key_to_table(self, key: str) -> None:
        """Add the specified key to the list of authorized keys. When adding
        the first one, we also disable password authentication (but give the
        user the ability to re-enable it)"""
        self.keys.append(key)
        if len(self.keys) == 1:
            self.form.pwauth.value = False
            if self.form.install_server:
                self.form.pwauth.enabled = True

    def remove_key_from_table(self, key: str) -> None:
        """Remove the specified key from the list of authorized keys. When
        removing the last one, we also re-enable password authentication (and
        disable the checkbox)."""
        self.keys.remove(key)
        if not self.keys:
            self.form.pwauth.value = True
            self.form.pwauth.enabled = False

    def show_key_overlay(self, key: str):
        self.show_stretchy_overlay(SSHShowKeyStretchy(self, key))

    def refresh_keys_table(self):
        rows: List[TableRow] = []

        if not self.keys:
            rows = [
                TableRow(
                    [
                        (
                            4,
                            Padding.push_2(
                                Color.info_minor(Text(_("No authorized key")))
                            ),
                        )
                    ]
                )
            ]
        for key in self.keys:
            menu = ActionMenu(
                [
                    Action(
                        label=_("Delete"),
                        enabled=True,
                        value="delete",
                        opens_dialog=False,
                    ),
                    Action(
                        label=_("Show"),
                        enabled=True,
                        value="show",
                        opens_dialog=True,
                    ),
                ]
            )

            rows.append(
                make_action_menu_row(
                    [
                        Text("["),
                        # LP: #2055702 wrap="ellipsis" looks better but it
                        # produces crashes on non UTF-8 and/or serial
                        # terminals,
                        # We can move back to wrap="ellipsis" when we switch to
                        # core24 or if the fix gets SRUd to jammy.
                        Text(key, wrap="clip"),
                        menu,
                        Text("]"),
                    ],
                    menu,
                )
            )
            connect_signal(menu, "action", self._action, user_args=[key])

        self.keys_table.set_contents(rows)

    def _action(self, key, sender, value):
        if value == "delete":
            self.remove_key_from_table(key)
            self.refresh_keys_table()
        elif value == "show":
            self.show_key_overlay(key)

    def _toggle_server(self, sender, installed: bool):
        self._import_key_btn.enabled = installed

        if installed:
            self.form.pwauth.enabled = bool(self.keys)
        else:
            self.form.pwauth.enabled = False
