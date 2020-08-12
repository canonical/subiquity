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

from subiquity.common.types import SSHData
from subiquity.controller import SubiquityController
from subiquity.ui.views.ssh import SSHView

log = logging.getLogger('subiquity.controllers.ssh')


class FetchSSHKeysFailure(Exception):
    def __init__(self, message, output):
        self.message = message
        self.output = output


class SSHController(SubiquityController):

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
        ssh_data = SSHData(
            install_server=self.model.install_server,
            allow_pw=self.model.pwauth)
        self.ui.set_body(SSHView(self, ssh_data))
        if self.answers:
            ssh_data = SSHData(
                install_server=self.answers.get("install_server", False),
                authorized_keys=self.answers.get("authorized_keys", []),
                allow_pw=self.answers.get("pwauth", True))
            self.done(ssh_data)
        elif 'ssh-import-id' in self.app.answers.get('Identity', {}):
            import_id = self.app.answers['Identity']['ssh-import-id']
            ssh_data = SSHData(install_server=True, allow_pw=True)
            self.fetch_ssh_keys(ssh_data, import_id)

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
        description="{ssh_import_id}")
    async def _fetch_ssh_keys(self, *, context, ssh_data, ssh_import_id):
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
            ssh_data.authorized_keys = key_material.splitlines()
            self.done(ssh_data)
        else:
            self.ui.body.confirm_ssh_keys(
                ssh_data, ssh_import_id, key_material, fingerprints)

    def fetch_ssh_keys(self, ssh_data, ssh_import_id):
        self._fetch_task = schedule_task(
            self._fetch_ssh_keys(
                ssh_data=ssh_data, ssh_import_id=ssh_import_id))

    def done(self, ssh_data):
        log.debug("SSHController.done next_screen result=%s", ssh_data)
        self.model.install_server = ssh_data.install_server
        self.model.authorized_keys = ssh_data.authorized_keys
        self.model.pwauth = ssh_data.allow_pw
        self.configured()
        self.app.next_screen()

    def make_autoinstall(self):
        return {
            'install-server': self.model.install_server,
            'authorized-keys': self.model.authorized_keys,
            'allow-pw': self.model.pwauth,
            }
