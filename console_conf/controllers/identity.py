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

import json

from subiquitycore.controllers.identity import BaseIdentityController
from subiquitycore.utils import disable_first_boot_service, run_command, mark_firstboot_complete

from console_conf.ui.views import IdentityView, LoginView


class IdentityController(BaseIdentityController):
    identity_view = IdentityView

    def default(self):
        title = "Profile setup"
        excerpt = "Enter an email address from your account in the store."
        footer = ""
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 40)
        self.ui.set_body(self.identity_view(self.model, self.signal, self.opts, self.loop))
        if self.is_device_owned():
            # FIXME: should be email rather than realname here, but extrausers only has email
            self.signal.emit_signal('identity:done', self.model.user.realname)

    def is_device_owned(self):
        """ Check if device is owned """

        # TODO: use proper snap APIs.
        with open('/var/lib/extrausers/passwd', 'r') as extrausers_fp:
            passwd_line = extrausers_fp.readline()
            if passwd_line and len(passwd_line) > 0:
                passwd = passwd_line.split(':')
                result = {
                    'realname': passwd[4].split(',')[0],
                    'username': passwd[0],
                    }
                self.model.add_user(result)
                return True
        return False

    def identity_done(self, email):
        if self.opts.dry_run:
            result = {
                'realname': email,
                'username': email,
                }
            self.model.add_user(result)
        elif self.is_device_owned():
            # user was added to the model, we don't need to do anything else.
            pass
        else:
            self.ui.frame.body.progress.set_text("Contacting store...")
            self.loop.draw_screen()
            result = run_command(["snap", "create-user", "--sudoer", "--json", email])
            self.progress.set_text("")
            if result['status'] != 0:
                self.ui.frame.body.error.set_text("Creating user failed:\n" + result['err'])
                return
            else:
                # mark ourselves complete
                mark_firstboot_complete()

                data = json.loads(result['output'])
                result = {
                    'realname': email,
                    'username': data['username'],
                    }
                self.model.add_user(result)
        self.signal.emit_signal('identity:login')

    def login(self):
        title = "Configuration Complete"
        footer = "View configured user and device access methods"
        self.ui.set_header(title)
        self.ui.set_footer(footer)

        net_model = self.controllers['Network'].model
        net_model.probe_network()
        configured_ifaces = net_model.get_configured_interfaces()
        login_view = LoginView(self.opts,
                               self.model,
                               self.signal,
                               self.model.user,
                               configured_ifaces)

        self.ui.set_body(login_view)

    def login_done(self):
        if not self.opts.dry_run:
            # stop the console-conf services (this will kill the current process).
            disable_first_boot_service()

        self.signal.emit_signal('quit')
