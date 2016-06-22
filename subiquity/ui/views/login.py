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
import copy
import logging
import os
from urwid import (ListBox, Pile, BoxAdapter, Text)
from subiquity.ui.lists import SimpleList
from subiquity.ui.buttons import finish_btn
from subiquity.ui.utils import Padding, Color
from subiquity.view import ViewPolicy
from subiquity import utils

log = logging.getLogger("subiquity.views.login")


class LoginView(ViewPolicy):
    def __init__(self, model, signal, user, ifaces):
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

    def auth_name(self, idstr):
        # lp:<id>
        # gh:<id>
        # sso:<id>
        auth_type = idstr.split(":")[0]
        auth_to_name = {
            'lp': 'Launchpad',
            'gh': 'Github',
            'sso': 'Ubuntu SSO'
        }
        return auth_to_name.get(auth_type, 'Unknown Authenication')

    def _build_model_inputs(self):
        """
        This device is registered to Ryan Harper.  Ryan Harper added
        a user, raharper, to the device for local access on the console.
        
        Remote access was enabled via authentication with Launchpad as
        lp:raharper and public ssh keys were added to the system for
        remote access.

        Ryan Harper can remotely connect to this system via SSH:

                     ssh rharper@192.168.11.58
                     ssh rharper@192.168.11.44
        """

        local_tpl = (
            "This device is registered to {realname}.  {realname} added a"
            " user, <{username}> to the device for access.")

        remote_tpl = (
            "\n\nRemote access was enabled via authentication with {auth} user"
            " <{ssh_import_id}>.\nPublic SSH keys were added to the device "
            "for remote access.\n\n{realname} can connect remotely to this "
            "device via SSH:")
        
        sl = []
        ssh = []
        user = self.model.user
        login_info = {
            'realname': user.realname,
            'username': user.username,
        }
        login_info.update({'auth': self.auth_name(user.ssh_import_id),
                           'ssh_import_id': user.ssh_import_id.split(":")[-1]})
        print(login_info)
        login_text = local_tpl.format(**login_info)
        if user.ssh_import_id:
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
        # mark ourselves complete 
        utils.mark_firstboot_complete()

        # disable the UI service restoring getty service
        utils.disable_first_boot_service()
    
        self.signal.emit_signal('quit')
