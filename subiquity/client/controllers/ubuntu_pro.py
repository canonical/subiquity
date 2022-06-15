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
""" Module that defines the client-side controller class for Ubuntu Pro. """

import asyncio
import logging
from typing import Callable, List, Optional

from subiquitycore.async_helpers import schedule_task

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import (
    UbuntuProInfo,
    UbuntuProCheckTokenStatus as TokenStatus,
    UbuntuProService,
    )
from subiquity.ui.views.ubuntu_pro import UbuntuProView

from subiquitycore.lsb_release import lsb_release
from subiquitycore.tuicontroller import Skip

log = logging.getLogger("subiquity.client.controllers.ubuntu_pro")


class UbuntuProController(SubiquityTuiController):
    """ Client-side controller for Ubuntu Pro configuration. """

    endpoint_name = "ubuntu_pro"

    def __init__(self, app) -> None:
        """ Initializer for the client-side UA controller. """
        self._check_task: Optional[asyncio.Future] = None

        super().__init__(app)

    async def make_ui(self) -> UbuntuProView:
        """ Generate the UI, based on the data provided by the model. """

        dry_run: bool = self.app.opts.dry_run

        lsb = lsb_release(dry_run=dry_run)
        # TODO Remove explicit check for jammy when 22.04 gets marked as a LTS
        # version instead of a "(development branch)".
        if "LTS" not in lsb["description"] and lsb["codename"] != "jammy":
            await self.endpoint.skip.POST()
            raise Skip("Not running LTS version")

        ubuntu_pro_info = await self.endpoint.GET()
        return UbuntuProView(self, ubuntu_pro_info.token)

    def run_answers(self) -> None:
        if "token" in self.answers:
            self.done(self.answers["token"])

    def check_token(self, token: str,
                    on_success: Callable[[List[UbuntuProService]], None],
                    on_failure: Callable[[TokenStatus], None],
                    ) -> None:
        """ Asynchronously check the token passed as an argument. """
        async def inner() -> None:
            answer = await self.endpoint.check_token.GET(token)
            if answer.status == TokenStatus.VALID_TOKEN:
                on_success(answer.services)
            else:
                on_failure(answer.status)

        self._check_task = schedule_task(inner())

    def cancel_check_token(self) -> None:
        """ Cancel the asynchronous token check (if started). """
        if self._check_task is not None:
            self._check_task.cancel()

    def cancel(self) -> None:
        self.app.prev_screen()

    def done(self, token: str) -> None:
        self.app.next_screen(
            self.endpoint.POST(UbuntuProInfo(token=token))
        )
