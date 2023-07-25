# Copyright 2023 Canonical, Ltd.
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

import enum
import logging
import os
import subprocess
from typing import List

from subiquity.common.types import SSHFetchIdStatus
from subiquitycore.utils import arun_command

log = logging.getLogger("subiquity.server.ssh")


class SSHFetchError(Exception):
    def __init__(self, status: SSHFetchIdStatus, reason: str) -> None:
        self.reason = reason
        self.status = status
        super().__init__()


class SSHKeyFetcher:
    def __init__(self, app):
        self.app = app

    async def fetch_keys_for_id(self, user_id: str) -> List[str]:
        cmd = ("ssh-import-id", "--output", "-", "--", user_id)
        env = None
        if self.app.base_model.proxy.proxy:
            env = os.environ.copy()
            env["https_proxy"] = self.app.base_model.proxy.proxy

        try:
            cp = await arun_command(cmd, check=True, env=env)
        except subprocess.CalledProcessError as exc:
            log.exception("ssh-import-id failed. stderr: %s", exc.stderr)
            raise SSHFetchError(status=SSHFetchIdStatus.IMPORT_ERROR, reason=exc.stderr)
        keys_material: str = cp.stdout.replace("\r", "").strip()
        return [mat for mat in keys_material.splitlines() if mat]

    async def gen_fingerprint_for_key(self, key: str) -> str:
        """For a given key, generate the fingerprint."""

        # ssh-keygen supports multiple keys at once, but it is simpler to
        # associate each key with its resulting fingerprint if we call
        # ssh-keygen multiple times.
        cmd = ("ssh-keygen", "-l", "-f", "-")
        try:
            cp = await arun_command(cmd, check=True, input=key)
        except subprocess.CalledProcessError as exc:
            log.exception("ssh-import-id failed. stderr: %s", exc.stderr)
            raise SSHFetchError(
                status=SSHFetchIdStatus.FINGERPRINT_ERROR, reason=exc.stderr
            )
        return cp.stdout.strip()


class DryRunSSHKeyFetcher(SSHKeyFetcher):
    class SSHImportStrategy(enum.Enum):
        SUCCESS = "success"
        FAILURE = "failure"

        RUN_ON_HOST = "run-on-host"

    async def fetch_keys_fake_success(self, user_id: str) -> List[str]:
        unused, username = user_id.split(":", maxsplit=1)
        return [
            f"""\
ssh-ed25519\
 AAAAC3NzaC1lZDI1NTE5AAAAIMM/qhS3hS3+IjpJBYXZWCqPKPH9Zag8QYbS548iEjoZ\
 {username}@earth # ssh-import-id {user_id}"""
        ]

    async def fetch_keys_fake_failure(self, user_id: str) -> List[str]:
        unused, username = user_id.split(":", maxsplit=1)
        raise SSHFetchError(
            status=SSHFetchIdStatus.IMPORT_ERROR,
            reason=f"ERROR Username {username} not found.",
        )

    async def fetch_keys_for_id(self, user_id: str) -> List[str]:
        service, username = user_id.split(":", maxsplit=1)
        strategy = self.SSHImportStrategy(self.app.dr_cfg.ssh_import_default_strategy)
        for entry in self.app.dr_cfg.ssh_imports:
            if entry["username"] != username:
                continue
            strategy = self.SSHImportStrategy(entry["strategy"])
            break

        strategies_mapping = {
            self.SSHImportStrategy.RUN_ON_HOST: super().fetch_keys_for_id,
            self.SSHImportStrategy.SUCCESS: self.fetch_keys_fake_success,
            self.SSHImportStrategy.FAILURE: self.fetch_keys_fake_failure,
        }

        coroutine = strategies_mapping[strategy](user_id)

        return await coroutine
