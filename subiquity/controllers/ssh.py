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
import subprocess

from subiquitycore.async_helpers import schedule_task
from subiquitycore.context import with_context
from subiquitycore import utils

from subiquity.controller import SubiquityTuiController
from subiquity.ui.views.ssh import SSHView

log = logging.getLogger('subiquity.controllers.ssh')


class FetchSSHKeysFailure(Exception):
    def __init__(self, message, output):
        self.message = message
        self.output = output


class SSHController(SubiquityTuiController):

    autoinstall_key = model_name = "ssh"
    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'install-server': {'type': 'boolean'},
            'authorized-keys': {
                'type': 'array',
                'items': {'type': 'string'},
                },
            'allow-pw': {'type': 'boolean'},
        },
    }

    def __init__(self, app):
        super().__init__(app)
        self._fetch_task = None

    def load_autoinstall_data(self, data):
        if data is None:
            return
        self.model.install_server = data.get('install-server', False)
        self.model.authorized_keys = data.get(
            'authorized-keys', [])
        self.model.pwauth = data.get(
            'allow-pw', not self.model.authorized_keys)

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
                "ssh_import_id": import_id.split(":", 1)[0],
                "import_username": import_id.split(":", 1)[1],
                "install_server": True,
                "pwauth": True,
            }
            self.fetch_ssh_keys(d)

    def cancel(self):
        self.app.prev_screen()

    def _fetch_cancel(self):
        if self._fetch_task is None:
            return
        self._fetch_task.cancel()

    async def run_cmd_checked(self, cmd, *, failmsg, **kw):
        cp = await utils.arun_command(cmd, **kw)
        if cp.returncode != 0:
            if isinstance(self.ui.body, SSHView):
                self.ui.body.fetching_ssh_keys_failed(failmsg, cp.stderr)
            raise subprocess.CalledProcessError(cp.returncode, cmd)
        return cp

    @with_context(
        name="ssh_import_id",
        description="{user_spec[ssh_import_id]}:{user_spec[import_username]}")
    async def _fetch_ssh_keys(self, *, context, user_spec):
        ssh_import_id = "{ssh_import_id}:{import_username}".format(**user_spec)
        with self.context.child("ssh_import_id", ssh_import_id):
            try:
                cp = await self.run_cmd_checked(
                    ['ssh-import-id', '-o-', ssh_import_id],
                    failmsg=_("Importing keys failed:"))
            except subprocess.CalledProcessError:
                return
            key_material = cp.stdout.replace('\r', '').strip()

            try:
                cp = await self.run_cmd_checked(
                    ['ssh-keygen', '-lf-'],
                    failmsg=_(
                        "ssh-keygen failed to show fingerprint of downloaded "
                        "keys:"),
                    input=key_material)
            except subprocess.CalledProcessError:
                return

            fingerprints = cp.stdout.replace(
                "# ssh-import-id {}".format(ssh_import_id),
                "").strip().splitlines()

            if 'ssh-import-id' in self.app.answers.get("Identity", {}):
                user_spec['authorized_keys'] = key_material.splitlines()
                self.done(user_spec)
            else:
                self.ui.body.confirm_ssh_keys(
                    user_spec, ssh_import_id, key_material, fingerprints)

    def fetch_ssh_keys(self, user_spec):
        self._fetch_task = schedule_task(
            self._fetch_ssh_keys(user_spec=user_spec))

    def done(self, result):
        log.debug("SSHController.done next_screen result=%s", result)
        self.model.install_server = result['install_server']
        self.model.authorized_keys = result.get('authorized_keys', [])
        self.model.pwauth = result.get('pwauth', True)
        self.model.ssh_import_id = result.get('ssh_import_id', None)
        self.configured()
        self.app.next_screen()

    def make_autoinstall(self):
        return {
            'install-server': self.model.install_server,
            'authorized-keys': self.model.authorized_keys,
            'allow-pw': self.model.pwauth,
            }
