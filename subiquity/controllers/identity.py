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
import subprocess

from subiquitycore.controller import BaseController
from subiquitycore.utils import run_command_start, run_command_summarize

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
        self.ui.set_header(title, excerpt)
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
                }
            if 'ssh_import_id' in self.answers:
                ssh_import_id = self.answers['ssh_import_id']
                self.fetch_ssh_keys(d, ssh_import_id)
            else:
                self.done(d)

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def _fetch_cancel(self):
        if self._fetching_proc is None:
            return
        try:
            self._fetching_proc.terminate()
        except ProcessLookupError:
            pass # It's OK if the process has already terminated.
        self._fetching_proc = None

    def _fetch_ssh_keys(self, result, p, ssh_import_id):
        stdout, stderr = p.communicate()
        if p != self._fetching_proc:
            log.debug("_fetch_ssh_keys cancelled")
            return None
        status = run_command_summarize(p, stdout, stderr)
        if status['status'] != 0:
            # Do better here!
            return None
        ssh_key = status['output']
        p = subprocess.Popen(
            ['ssh-keygen', '-lf-'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        stdout, stderr = p.communicate(input=ssh_key.encode('latin-1'))
        if p.returncode != 0:
            # Do better here!
            return None
        fingerprint = stdout.decode('utf-8')
        fingerprint = fingerprint.replace("# ssh-import-id {} ".format(ssh_import_id), "")
        return True, result, ssh_key, fingerprint

    def _fetched_ssh_keys(self, fut):
        result = fut.result()
        log.debug("_fetched_ssh_keys %s", result)
        if result is not None:
            ok, result, ssh_key, fingerprint = result
            if ok:
                 if self.answers.get('accept-ssh-key'):
                    result['ssh_key'] = ssh_key
                    self.loop.set_alarm_in(0.0, lambda loop, ud: self.done(result))
                 else:
                    self.ui.frame.body.confirm_ssh_keys(result, ssh_key, fingerprint)

    def fetch_ssh_keys(self, result, ssh_import_id):
        self._fetching_proc = run_command_start(['ssh-import-id', '-o-', ssh_import_id])
        self.run_in_bg(
            lambda: self._fetch_ssh_keys(result, self._fetching_proc, ssh_import_id),
            self._fetched_ssh_keys)

    def done(self, result):
        log.debug("User input: {}".format(result))
        self.model.add_user(result)
        self.signal.emit_signal('installprogress:identity-config-done')
        self.signal.emit_signal('next-screen')
