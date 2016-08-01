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

""" Login

Login provides user with language selection

"""
import logging
import os

from urwid import (ListBox, Pile, Text)

from subiquitycore.ui.buttons import finish_btn
from subiquitycore.ui.utils import Color, Padding
from subiquitycore.view import BaseView
from subiquitycore import utils

log = logging.getLogger("subiquitycore.views.login")


class LoginView(BaseView):
    def __init__(self, opts, model, signal, user, ifaces):
        self.opts = opts
        self.model = model
        self.signal = signal
        self.user = user
        self.ifaces = ifaces
        self.items = []
        self.body = [
            Padding.line_break(""),
            Padding.line_break(""),
            Padding.line_break(""),
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        super().__init__(ListBox(self.body))

    def _build_buttons(self):
        self.buttons = [
            Color.button(finish_btn(on_press=self.done),
                         focus_map='button focus'),
        ]
        return Pile(self.buttons)

    def _build_model_inputs(self):
        local_tpl = (
            "This device is registered to {realname}.")

        remote_tpl = (
            "\n\nRemote access was enabled via authentication with SSO user"
            " <{username}>.\nPublic SSH keys were added to the device "
            "for remote access.\n\n{realname} can connect remotely to this "
            "device via SSH:")

        sl = []
        ssh = []
        user = self.model.user
        login_info = {
            'realname': user.realname,
            'username': user.username,
        }
        login_text = local_tpl.format(**login_info)
        login_text += remote_tpl.format(**login_info)
        for iface in self.ifaces:
            ip = str(iface.ip).split("/")[0]
            ssh_iface = "    ssh %s@%s" % (user.username, ip)
            ssh += [Padding.center_50(Text(ssh_iface))]

        sl += [Text(login_text),
               Padding.line_break("")] + ssh

        return Pile(sl)

    def confirm(self, result):
        self.done()

    def done(self, button):
        if not self.opts.dry_run:
            os.unlink("/etc/systemd/getty@.service")
            os.unlink("/etc/systemd/serial-getty@.service")
            utils.run_command(["systemctl", "daemon-reload"])
            # This will kill the running process.
            utils.run_command(["systemctl", "try-restart", "getty@*.service", "serial-getty@*.service"])

        self.signal.emit_signal('quit')
