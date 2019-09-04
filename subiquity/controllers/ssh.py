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

from subiquitycore.controller import BaseController
from subiquitycore import utils

from subiquity.ui.views.ssh import SSHView

log = logging.getLogger('subiquity.controllers.ssh')


class FetchSSHKeysFailure(Exception):
    def __init__(self, message, output):
        self.message = message
        self.output = output


class SSHController(BaseController):

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model.ssh

    def start_ui(self):
        self.ui.set_body(SSHView(self.model, self))
        if self.answers:
            d = {
                "install_server": self.answers.get("install_server", False),
                "authorized_keys": self.answers.get("authorized_keys", []),
                "pwauth": self.answers.get("pwauth", True),
            }
            self.done(d)
        elif 'ssh-import-id' in self.app.answers.get('Identity', {}):
            import_id = self.app.answers['Identity']['ssh-import-id']
            d = {
                "install_server": True,
                "pwauth": True,
            }
            self.fetch_ssh_keys(d, import_id)

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def _fetch_cancel(self):
        if self._fetching_proc is None:
            return
        try:
            self._fetching_proc.terminate()
        except ProcessLookupError:
            pass  # It's OK if the process has already terminated.
        self._fetching_proc = None

    def _bg_fetch_ssh_keys(self, user_spec, proc, ssh_import_id):
        stdout, stderr = proc.communicate()
        stdout = stdout.decode('utf-8', errors='replace')
        stderr = stderr.decode('utf-8', errors='replace')
        log.debug("ssh-import-id exited with code %s", proc.returncode)
        if proc != self._fetching_proc:
            log.debug("_fetch_ssh_keys cancelled")
            return None
        if proc.returncode != 0:
            raise FetchSSHKeysFailure(_("Importing keys failed:"), stderr)
        key_material = stdout.replace('\r', '').strip()

        cp = utils.run_command(['ssh-keygen', '-lf-'], input=key_material)
        if cp.returncode != 0:
            return FetchSSHKeysFailure(_("ssh-keygen failed to show "
                                         "fingerprint of downloaded keys:"),
                                       cp.stderr)
        fingerprints = (
            cp.stdout.replace("# ssh-import-id {} ".format(ssh_import_id),
                              "").strip().splitlines())

        return user_spec, ssh_import_id, key_material, fingerprints

    def _fetched_ssh_keys(self, fut):
        if not isinstance(self.ui.body, SSHView):
            # This can happen if curtin failed while the keys where being
            # fetched and we jump to the log view.
            log.debug(
                "view is now an instance of %s, not SSHView",
                type(self.ui.body))
            return
        try:
            result = fut.result()
        except FetchSSHKeysFailure as e:
            log.debug("fetching ssh keys failed %s", e)
            self.ui.body.fetching_ssh_keys_failed(e.message, e.output)
        else:
            log.debug("_fetched_ssh_keys %s", result)
            if result is None:
                # Happens if the fetch is cancelled.
                return
            user_spec, ssh_import_id, key_material, fingerprints = result
            if 'ssh-import-id' in self.app.answers.get("Identity", {}):
                user_spec['authorized_keys'] = key_material.splitlines()
                self.loop.set_alarm_in(0.0,
                                       lambda loop, ud: self.done(user_spec))
            else:
                self.ui.body.confirm_ssh_keys(
                    user_spec, ssh_import_id, key_material, fingerprints)

    def fetch_ssh_keys(self, user_spec, ssh_import_id):
        log.debug("User input: %s, fetching ssh keys for %s",
                  user_spec, ssh_import_id)
        self._fetching_proc = utils.start_command(['ssh-import-id', '-o-',
                                                   ssh_import_id])
        self.run_in_bg(
            lambda: self._bg_fetch_ssh_keys(user_spec, self._fetching_proc,
                                            ssh_import_id),
            self._fetched_ssh_keys)

    def done(self, result):
        log.debug("SSHController.done next-screen result=%s", result)
        self.model.install_server = result['install_server']
        self.model.authorized_keys = result.get('authorized_keys', [])
        self.model.pwauth = result.get('pwauth', True)
        self.model.ssh_import_id = result.get('ssh_import_id', None)
        self.signal.emit_signal('installprogress:ssh-config-done')
        self.signal.emit_signal('next-screen')
