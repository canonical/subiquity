# Copyright 2021 Canonical, Ltd.
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
""" Module that defines the client-side controller class for Ubuntu Advantage.
"""

import logging

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import UbuntuAdvantageInfo
from subiquity.ui.views.ubuntu_advantage import UbuntuAdvantageView

from subiquitycore.lsb_release import lsb_release
from subiquitycore.tuicontroller import Skip

log = logging.getLogger("subiquity.client.controllers.ubuntu_advantage")


class UbuntuAdvantageController(SubiquityTuiController):
    """ Client-side controller for Ubuntu Advantage configuration. """

    endpoint_name = "ubuntu_advantage"

    async def make_ui(self) -> UbuntuAdvantageView:
        """ Generate the UI, based on the data provided by the model. """

        # TODO remove these two lines to enable this screen
        await self.endpoint.skip.POST()
        raise Skip("Hiding the screen until we can validate the token.")

        dry_run: bool = self.app.opts.dry_run
        if "LTS" not in lsb_release(dry_run=dry_run)["description"]:
            await self.endpoint.skip.POST()
            raise Skip("Not running LTS version")

        ubuntu_advantage_info = await self.endpoint.GET()
        return UbuntuAdvantageView(self, ubuntu_advantage_info.token)

    def run_answers(self) -> None:
        if "token" in self.answers:
            self.done(self.answers["token"])

    def cancel(self) -> None:
        self.app.prev_screen()

    def done(self, token: str) -> None:
        log.debug("UbuntuAdvantageController.done token=%s", token)
        self.app.next_screen(
            self.endpoint.POST(UbuntuAdvantageInfo(token=token))
        )
