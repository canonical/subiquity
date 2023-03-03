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

import asyncio
import logging

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import SSHFetchIdResponse, SSHFetchIdStatus
from subiquity.ui.views.ssh import IMPORT_KEY_LABEL, ConfirmSSHKeys, SSHView
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

    async def run_answers(self):
        import subiquitycore.testing.view_helpers as view_helpers

        form = self.app.ui.body.form
        form.install_server.value = self.answers.get("install_server", False)
        form.pwauth.value = self.answers.get("pwauth", True)

        for key in self.answers.get("authorized_keys", []):
            # We don't have GUI support for this.
            self.app.ui.body.add_key_to_table(key)

        if "ssh-import-id" in self.answers:
            view_helpers.click(
                view_helpers.find_button_matching(self.app.ui.body, IMPORT_KEY_LABEL)
            )
            service, username = self.answers["ssh-import-id"].split(":", maxsplit=1)
            if service not in ("gh", "lp"):
                raise ValueError(
                    f"invalid service {service} - only gh and lp are supported"
                )

            import_form = self.app.ui.body._w.stretchy.form

            view_helpers.enter_data(
                import_form, {"import_username": username, "ssh_import_id": service}
            )

            import_form._click_done(None)

            # Wait until the key gets fetched
            while True:
                try:
                    confirm_overlay = self.ui.body._w.stretchy
                except AttributeError:
                    pass
                else:
                    if isinstance(confirm_overlay, ConfirmSSHKeys):
                        break
                await asyncio.sleep(0.01)

            confirm_overlay.ok(None)

        form._click_done(None)

    def cancel(self):
        self.app.prev_screen()

    def _fetch_cancel(self):
        if self._fetch_task is None:
            return
        self._fetch_task.cancel()

    @with_context(name="ssh_import_id", description="{ssh_import_id}")
    async def _fetch_ssh_keys(self, *, context, ssh_import_id):
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

            if isinstance(self.ui.body, SSHView):
                self.ui.body.confirm_ssh_keys(ssh_import_id, identities)
            else:
                log.debug(
                    "ui.body of unexpected instance: %s", type(self.ui.body).__name__
                )

    def fetch_ssh_keys(self, ssh_import_id):
        self._fetch_task = schedule_task(
            self._fetch_ssh_keys(ssh_import_id=ssh_import_id)
        )

    def done(self, result):
        log.debug("SSHController.done next_screen result=%s", result)
        self.app.next_screen(self.endpoint.POST(result))
