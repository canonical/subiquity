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
import os
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


class SSHFetchError(Exception):
    def __init__(self, status: SSHFetchIdStatus, reason: str) -> None:
        self.reason = reason
        self.status = status
        super().__init__()


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

    async def fetch_keys_for_id(self, user_id: str) -> List[str]:
        cmd = ('ssh-import-id', '--output', '-', '--', user_id)
        env = None
        if self.app.base_model.proxy.proxy:
            env = os.environ.copy()
            env["https_proxy"] = self.app.base_model.proxy.proxy

        try:
            cp = await arun_command(cmd, check=True, env=env)
        except subprocess.CalledProcessError as exc:
            log.exception("ssh-import-id failed. stderr: %s", exc.stderr)
            raise SSHFetchError(status=SSHFetchIdStatus.IMPORT_ERROR,
                                reason=exc.stderr)
        keys_material: str = cp.stdout.replace('\r', '').strip()
        return [mat for mat in keys_material.splitlines() if mat]

    async def gen_fingerprint_for_key(self, key: str) -> str:
        """ For a given key, generate the fingerprint. """

        # ssh-keygen supports multiple keys at once, but it is simpler to
        # associate each key with its resulting fingerprint if we call
        # ssh-keygen multiple times.
        cmd = ('ssh-keygen', '-l', '-f', '-')
        try:
            cp = await arun_command(cmd, check=True, input=key)
        except subprocess.CalledProcessError as exc:
            log.exception("ssh-import-id failed. stderr: %s", exc.stderr)
            raise SSHFetchError(status=SSHFetchIdStatus.FINGERPRINT_ERROR,
                                reason=exc.stderr)
        return cp.stdout.strip()

    async def fetch_id_GET(self, user_id: str) -> SSHFetchIdResponse:
        identities: List[SSHIdentity] = []

        try:
            for key_material in await self.fetch_keys_for_id(user_id):
                fingerprint = await self.gen_fingerprint_for_key(key_material)

                fingerprint = fingerprint.replace(
                        f'# ssh-import-id {user_id}', ''
                        ).strip()

                key_type, key, key_comment = key_material.split(
                        ' ', maxsplit=2)
                identities.append(SSHIdentity(
                    key_type=key_type, key=key, key_comment=key_comment,
                    key_fingerprint=fingerprint
                ))
            return SSHFetchIdResponse(status=SSHFetchIdStatus.OK,
                                      identities=identities, error=None)

        except SSHFetchError as exc:
            return SSHFetchIdResponse(status=exc.status,
                                      identities=None, error=exc.reason)
