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

from subiquitycore.controller import BaseController
from subiquitycore.user import create_user

from subiquity.ui.views import IdentityView

log = logging.getLogger('subiquity.controllers.identity')


class IdentityController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.identity
        self.answers = self.all_answers.get('Identity', {})

    def default(self):
        title = _("Profile setup")
        excerpt = _("Enter the username and password (or ssh identity) you will use to log in to the system.")
        footer = ""
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(IdentityView(self.model, self, self.opts))
        if 'realname' in self.answers and \
            'username' in self.answers and \
            'password' in self.answers and \
            'hostname' in self.answers:
            d = {
                'realname': self.answers['realname'],
                'username': self.answers['username'],
                'hostname': self.answers['hostname'],
                'password': self.answers['password'],
                'confirm_password': self.answers['password'],
                'ssh_import_id': self.answers.get('ssh-import-id', ''),
                }
            self.create_user(d)

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def create_user(self, result):
        log.debug("User input: {}".format(result))
        self.model.add_user(result)
        try:
            create_user(result, dryrun=self.opts.dry_run)
        except PermissionError:
            log.exception('Failed to write curtin post-install config')
            self.signal.emit_signal('filesystem:error',
                                    'curtin_write_postinst_config', result)
            return None
        self.signal.emit_signal('installprogress:identity-config-done')
        # show next view
        self.signal.emit_signal('next-screen')
