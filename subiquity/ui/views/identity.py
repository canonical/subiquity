# Copyright 2015 Canonical, Ltd.
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

from urwid import Pile, Columns, Text, ListBox

from subiquitycore.curtin import curtin_write_postinst_config
from subiquitycore.ui.buttons import done_btn, cancel_btn
from subiquitycore.ui.interactive import (PasswordEditor,
                                          RealnameEditor,
                                          StringEditor,
                                          UsernameEditor)
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.user import create_user
from subiquitycore.view import BaseView


log = logging.getLogger("subiquity.views.identity")

HOSTNAME_MAXLEN = 64
REALNAME_MAXLEN = 160
SSH_IMPORT_MAXLEN = 256 + 3  # account for lp: or gh:
USERNAME_MAXLEN = 32


class IdentityView(BaseView):
    def __init__(self, model, controller, opts):
        self.model = model
        self.controller = controller
        self.signal = controller.signal
        self.opts = opts
        self.items = []
        self.realname = RealnameEditor(caption="")
        self.hostname = UsernameEditor(caption="")
        self.username = UsernameEditor(caption="")
        self.password = PasswordEditor(caption="")
        self.ssh_import_id = StringEditor(caption="")
        self.ssh_import_confirmed = True
        self.error = Text("", align="center")
        self.confirm_password = PasswordEditor(caption="")

        body = [
            Padding.center_90(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_90(Color.info_error(self.error)),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons()),
        ]
        super().__init__(ListBox(body))

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def _build_model_inputs(self):
        sl = [
            Columns(
                [
                    ("weight", 0.2, Text("Your name:", align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.realname,
                                        focus_map="string_input focus"))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Your server's name:",
                                         align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.hostname,
                                        focus_map="string_input focus"))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("", align="right")),
                    ("weight", 0.3, Color.info_minor(
                        Text("The name it uses when it talks to "
                             "other computers", align="left"))),
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Pick a username:", align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.username,
                                        focus_map="string_input focus"))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Choose a password:", align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.password,
                                        focus_map="string_input focus"))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Confirm your password:",
                                         align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.confirm_password,
                                        focus_map="string_input focus"))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Import SSH identity:",
                                         align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.ssh_import_id,
                                        focus_map="string_input focus"))
                ],
                dividechars=4
            ),

            Columns(
                [
                    ("weight", 0.2, Text("", align="right")),
                    ("weight", 0.3, Color.info_minor(
                        Text("Input your SSH user id from "
                             "Ubuntu SSO (sso:email), "
                             "Launchpad (lp:username) or "
                             "Github (gh:username).",
                             align="left"))),
                ],
                dividechars=4
            ),
        ]
        return Pile(sl)

    def done(self, result):
        # check in display order:
        #   realname, hostname, username, password, ssh
        if len(self.realname.value) < 1:
            self.error.set_text("Realname missing.")
            self.realname.value = ""
            return

        if len(self.realname.value) > REALNAME_MAXLEN:
            self.error.set_text("Realname too long, must be < " +
                                str(REALNAME_MAXLEN))
            self.realname.value = ""
            return

        if len(self.hostname.value) < 1:
            self.error.set_text("Server name missing.")
            self.hostname.value = ""
            return

        if len(self.hostname.value) > HOSTNAME_MAXLEN:
            self.error.set_text("Server name too long, must be < " +
                                str(HOSTNAME_MAXLEN))
            self.hostname.value = ""
            return

        if len(self.username.value) < 1:
            self.error.set_text("Username missing.")
            self.username.value = ""
            return

        if len(self.username.value) > USERNAME_MAXLEN:
            self.error.set_text("Username too long, must be < " +
                                str(USERNAME_MAXLEN))
            self.username.value = ""
            return

        if len(self.password.value) < 1:
            self.error.set_text("Password must be set")
            self.password.value = ""
            self.confirm_password.value = ""
            return

        if self.password.value != self.confirm_password.value:
            self.error.set_text("Passwords do not match.")
            self.password.value = ""
            self.confirm_password.value = ""
            return

        # ssh_id is optional
        if len(self.ssh_import_id.value) > SSH_IMPORT_MAXLEN:
            self.error.set_text("SSH id too long, must be < " +
                                str(SSH_IMPORT_MAXLEN))
            self.ssh_import_id.value = ""
            return

        cpassword = self.model.encrypt_password(self.password.value)
        log.debug("*crypted* User input: {} {} {}".format(
            self.username.value, cpassword, cpassword))
        result = {
            "hostname": self.hostname.value,
            "realname": self.realname.value,
            "username": self.username.value,
            "password": cpassword,
            "confirm_password": cpassword,
        }

        # if user specifed a value, allow user to validate fingerprint
        if self.ssh_import_id.value:
            if self.ssh_import_confirmed is True:
                result.update({'ssh_import_id': self.ssh_import_id.value})
            else:
                self.emit_signal('identity:confirm-ssh-id',
                                 self.ssh_import_id.value)
                return

        log.debug("User input: {}".format(result))
        self.model.add_user(result)

        self.create_user(result)

        self.signal.emit_signal('installprogress:wrote-postinstall')
        # show next view
        self.signal.emit_signal('menu:installprogress:main')

    def create_user(self, result):
        try:
            curtin_write_postinst_config(result)
            create_user(result, dryrun=self.opts.dry_run)
        except PermissionError:
            log.exception('Failed to write curtin post-install config')
            self.signal.emit_signal('filesystem:error',
                                    'curtin_write_postinst_config', result)
            return None

    def cancel(self, button):
        self.signal.prev_signal()
