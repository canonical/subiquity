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
import pwd

from urwid import (Pile, Columns, Text, ListBox)
from subiquitycore.ui.buttons import done_btn, cancel_btn
from subiquitycore.ui.interactive import EmailEditor
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.utils import run_command
from subiquitycore.view import BaseView

log = logging.getLogger("console_conf.views.identity")


'''
+---------------------------------------------------+
|                                                   |
| Enter the email address of the account in the     |
| store                                             |
|                                                   |
|                   +-------------------------+     |
|    Email address: |                         |     |
|                   +-------------------------+     |
|                                                   |
|                                                   |
|                         +--------+                |
|                         | Done   |                |
|                         +--------+                |
|                         | Cancel |                |
|                         +--------+                |
|                                                   |
+---------------------------------------------------+
'''

class IdentityView(BaseView):

    def __init__(self, model, signal, opts, loop):
        self.model = model
        self.signal = signal
        self.opts = opts
        self.loop = loop
        self.items = []
        self.email = EmailEditor(caption="")
        self.error = Text("", align="center")
        self.progress = Text("", align="center")

        body = [
            Padding.center_90(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_90(Color.info_error(self.error)),
            Padding.center_90(self.progress),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons()),
        ]
        super().__init__(ListBox(body))

    def _build_model_inputs(self):
        sl = [
            Columns(
                [
                    ("weight", 0.2, Text("Email address:", align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.email,
                                        focus_map="string_input focus"))
                ],
                dividechars=4
            ),
        ]
        return Pile(sl)

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def cancel(self, button):
        self.signal.prev_signal()

    def done(self, button):
        if len(self.email.value) < 1:
            self.error.set_text("Please enter an email address.")
            return
        if not self.opts.dry_run:
            self.progress.set_text("Contacting store...")
            self.loop.draw_screen()
            users_before = users()
            result = run_command(["snap", "create-user", self.email.value])
            self.progress.set_text("")
            if result['status'] != 0:
                self.error.set_text("Creating user failed:\n" + result['err'])
                return
            else:
                users_after = users()
                new_users = users_after - users_before
                if len(new_users) != 1:
                    self.error.set_text("uhh")
                    return
                new_user = pwd.getpwnam(new_users.pop())
                # Use email for realname until
                # https://bugs.launchpad.net/snappy/+bug/1607121 is resolved.
                result = {
                    'realname': self.email.value, #new_user.pw_gecos.split(",")[0]
                    'username': new_user.pw_name,
                    'passwod': '',
                    'confirm_password': ''
                    }
                # Work around https://bugs.launchpad.net/snappy/+bug/1606815
                run_command(["chown", "{}:{}".format(new_user.pw_uid, new_user.pw_gid), "-R", new_user.pw_dir])
                self.model.add_user(result)
        else:
                result = {
                    'realname': self.email.value,
                    'username': self.email.value,
                    'passwod': '',
                    'confirm_password': '',
                    }
                self.model.add_user(result)
        self.signal.emit_signal('menu:identity:login:main')

def users():
    r = set()
    for pw in pwd.getpwall():
        r.add(pw.pw_name)
    return r
