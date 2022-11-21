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
from typing import List

from subiquitycore.utils import arun_command
from subiquity.common.apidef import API
from subiquity.common.types import (
    SSHData,
    SSHFetchIdResponse,
    SSHFetchIdStatus,
    SSHIdentity,
    )
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.ssh')


class SSHController(SubiquityController):

    endpoint = API.ssh

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

    def load_autoinstall_data(self, data):
        if data is None:
            return
        self.model.install_server = data.get('install-server', False)
        self.model.authorized_keys = data.get('authorized-keys', [])
        self.model.pwauth = data.get(
            'allow-pw', not self.model.authorized_keys)

    def make_autoinstall(self):
        return {
            'install-server': self.model.install_server,
            'authorized-keys': self.model.authorized_keys,
            'allow-pw': self.model.pwauth,
            }

    async def GET(self) -> SSHData:
        return SSHData(
            install_server=self.model.install_server,
            allow_pw=self.model.pwauth)

    async def POST(self, data: SSHData) -> None:
        self.model.install_server = data.install_server
        self.model.authorized_keys = data.authorized_keys
        self.model.pwauth = data.allow_pw
        await self.configured()

    async def fetch_id_GET(self, user_id: str) -> SSHFetchIdResponse:
        identities: List[SSHIdentity] = []

        import_command = ('ssh-import-id', '--output', '-', '--', user_id)
        try:
            cp = await arun_command(import_command, check=True)
        except subprocess.CalledProcessError as e:
            log.exception("ssh-import-id failed. stderr: %s", e.stderr)
            return SSHFetchIdResponse(status=SSHFetchIdStatus.IMPORT_ERROR,
                                      identities=None, error=e.stderr)
        keys_material: str = cp.stdout.replace('\r', '').strip()

        # ssh-keygen supports multiple keys at once.
        fingerprint_command = ('ssh-keygen', '-l', '-f', '-')
        try:
            cp = await arun_command(fingerprint_command, check=True,
                                    input=keys_material)
        except subprocess.CalledProcessError as e:
            log.exception("ssh-import-id failed. stderr: %s", e.stderr)
            return SSHFetchIdResponse(
                    tatus=SSHFetchIdStatus.FINGERPRINT_ERROR,
                    identities=None, error=e.stderr)

        fingerprints: str = cp.stdout.replace(
                f'# ssh-import-id {user_id}', '').strip()

        zipped = zip(
                [mat for mat in keys_material.splitlines() if mat],
                fingerprints.splitlines())

        for key_material, fingerprint in zipped:
            key_type, key, key_comment = key_material.split(' ', maxsplit=2)
            identities.append(SSHIdentity(
                key_type=key_type, key=key, key_comment=key_comment,
                key_fingerprint=fingerprint
            ))
        return SSHFetchIdResponse(status=SSHFetchIdStatus.OK,
                                  identities=identities, error=None)
