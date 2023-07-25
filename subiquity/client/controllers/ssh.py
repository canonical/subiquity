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

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import SSHData, SSHFetchIdResponse, SSHFetchIdStatus
from subiquity.ui.views.ssh import SSHView
from subiquitycore.async_helpers import schedule_task
from subiquitycore.context import with_context

log = logging.getLogger("subiquity.client.controllers.ssh")


class FetchSSHKeysFailure(Exception):
    def __init__(self, message, output):
        self.message = message
        self.output = output


class SSHController(SubiquityTuiController):
    endpoint_name = "ssh"

    def __init__(self, app):
        super().__init__(app)
        self._fetch_task = None
        if not self.answers:
            identity_answers = self.app.answers.get("Identity", {})
            if "ssh-import-id" in identity_answers:
                self.answers["ssh-import-id"] = identity_answers["ssh-import-id"]

    async def make_ui(self):
        ssh_data = await self.endpoint.GET()
        return SSHView(self, ssh_data)

    def run_answers(self):
        if "ssh-import-id" in self.answers:
            import_id = self.answers["ssh-import-id"]
            ssh = SSHData(install_server=True, authorized_keys=[], allow_pw=True)
            self.fetch_ssh_keys(ssh_import_id=import_id, ssh_data=ssh)
        else:
            ssh = SSHData(
                install_server=self.answers.get("install_server", False),
                authorized_keys=self.answers.get("authorized_keys", []),
                allow_pw=self.answers.get("pwauth", True),
            )
            self.done(ssh)

    def cancel(self):
        self.app.prev_screen()

    def _fetch_cancel(self):
        if self._fetch_task is None:
            return
        self._fetch_task.cancel()

    @with_context(name="ssh_import_id", description="{ssh_import_id}")
    async def _fetch_ssh_keys(self, *, context, ssh_import_id, ssh_data):
        with self.context.child("ssh_import_id", ssh_import_id):
            response: SSHFetchIdResponse = await self.endpoint.fetch_id.GET(
                ssh_import_id
            )

            if response.status == SSHFetchIdStatus.IMPORT_ERROR:
                if isinstance(self.ui.body, SSHView):
                    self.ui.body.fetching_ssh_keys_failed(
                        _("Importing keys failed:"), response.error
                    )
                return
            elif response.status == SSHFetchIdStatus.FINGERPRINT_ERROR:
                if isinstance(self.ui.body, SSHView):
                    self.ui.body.fetching_ssh_keys_failed(
                        _("ssh-keygen failed to show fingerprint of downloaded keys:"),
                        response.error,
                    )
                return

            identities = response.identities

            if "ssh-import-id" in self.app.answers.get("Identity", {}):
                ssh_data.authorized_keys = [
                    id_.to_authorized_key() for id_ in identities
                ]
                self.done(ssh_data)
            else:
                if isinstance(self.ui.body, SSHView):
                    self.ui.body.confirm_ssh_keys(ssh_data, ssh_import_id, identities)
                else:
                    log.debug(
                        "ui.body of unexpected instance: %s",
                        type(self.ui.body).__name__,
                    )

    def fetch_ssh_keys(self, ssh_import_id, ssh_data):
        self._fetch_task = schedule_task(
            self._fetch_ssh_keys(ssh_import_id=ssh_import_id, ssh_data=ssh_data)
        )

    def done(self, result):
        log.debug("SSHController.done next_screen result=%s", result)
        self.app.next_screen(self.endpoint.POST(result))
