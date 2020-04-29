# Copyright 2019 Canonical, Ltd.
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

from subiquitycore.async_helpers import schedule_task
from subiquitycore.controllers.network import NetworkController

from subiquity.controller import SubiquityController
from subiquity.controllers.error import ErrorReportKind


log = logging.getLogger("subiquity.controllers.network")


class NetworkController(NetworkController, SubiquityController):

    ai_data = None
    autoinstall_key = "network"
    autoinstall_schema = {
        'type': 'object',
        'properties': {
            'version': {
                'type': 'integer',
                'minimum': 2,
                'maximum': 2,
                },
            'ethernets': {'type': 'object'},
            'wifis': {'type': 'object'},
            'bridges': {'type': 'object'},
            'bonds': {'type': 'object'},
            'tunnels': {'type': 'object'},
            'vlans': {'type': 'object'},
            },
        }

    def __init__(self, app):
        super().__init__(app)
        app.note_file_for_apport("NetplanConfig", self.netplan_path)

    def load_autoinstall_data(self, data):
        self.ai_data = data

    def start(self):
        if self.ai_data is not None:
            self.apply_config()
        elif not self.interactive():
            self.initial_delay = schedule_task(self.delay())
        super().start()

    async def delay(self):
        await asyncio.sleep(10)

    async def apply_autoinstall_config(self):
        if self.ai_data is None:
            await self.initial_delay
            self.update_initial_configs()
            self.apply_config()
        await self.apply_config_task.wait()
        self.model.has_network = bool(
            self.network_event_receiver.default_routes)

    def render_config(self):
        if self.ai_data is not None:
            r = self.ai_data
            if self.interactive():
                # If we're interactive, we want later renders to
                # incorporate any changes from the UI.
                self.ai_data = None
            return r
        return super().render_config()

    async def _apply_config(self, silent):
        try:
            await super()._apply_config(silent)
        except asyncio.CancelledError:
            # asyncio.CancelledError is a subclass of Exception in
            # Python 3.6 (sadface)
            raise
        except Exception:
            log.exception("_apply_config failed")
            self.model.has_network = False
            self.app.make_apport_report(
                ErrorReportKind.NETWORK_FAIL, "applying network",
                interrupt=True)
            if not self.interactive():
                raise

    def done(self):
        self.configured()
        super().done()

    def make_autoinstall(self):
        return self.model.render_config()['network']
