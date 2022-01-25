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
import os

from subiquitycore.async_helpers import schedule_task

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.ubuntu_advantage import (
    InvalidUATokenError,
    ExpiredUATokenError,
    CheckSubscriptionError,
    UAInterface,
    UAInterfaceStrategy,
    MockedUAInterfaceStrategy,
    UAClientUAInterfaceStrategy,
)
from subiquity.common.types import UbuntuAdvantageInfo
from subiquity.ui.views.ubuntu_advantage import UbuntuAdvantageView

from subiquitycore.lsb_release import lsb_release
from subiquitycore.tuicontroller import Skip

log = logging.getLogger("subiquity.client.controllers.ubuntu_advantage")


class UbuntuAdvantageController(SubiquityTuiController):
    """ Client-side controller for Ubuntu Advantage configuration. """

    endpoint_name = "ubuntu_advantage"

    def __init__(self, app):
        """ Initializer for client-side UA controller. """
        strategy: UAInterfaceStrategy
        if app.opts.dry_run:
            strategy = MockedUAInterfaceStrategy(scale_factor=app.scale_factor)
        else:
            # Make sure we execute `$PYTHON "$SNAP/usr/bin/ubuntu-advantage"`.
            executable = (
                os.environ["PYTHON"],
                os.path.join(os.environ["SNAP"], "usr/bin/ubuntu-advantage"),
            )
            strategy = UAClientUAInterfaceStrategy(executable=executable)
        self.ua_interface = UAInterface(strategy)
        super().__init__(app)

    async def make_ui(self) -> UbuntuAdvantageView:
        """ Generate the UI, based on the data provided by the model. """

        dry_run: bool = self.app.opts.dry_run
        if "LTS" not in lsb_release(dry_run=dry_run)["description"]:
            await self.endpoint.skip.POST()
            raise Skip("Not running LTS version")

        ubuntu_advantage_info = await self.endpoint.GET()
        return UbuntuAdvantageView(self, ubuntu_advantage_info.token)

    def run_answers(self) -> None:
        if "token" in self.answers:
            self.done(self.answers["token"])

    def check_token(self, token: str):
        """ Asynchronously check the token passed as an argument. """
        async def inner() -> None:
            try:
                svcs = await \
                        self.ua_interface.get_activable_services(token=token)
            except InvalidUATokenError:
                if isinstance(self.ui.body, UbuntuAdvantageView):
                    self.ui.body.show_invalid_token()
            except ExpiredUATokenError:
                if isinstance(self.ui.body, UbuntuAdvantageView):
                    self.ui.body.show_expired_token()
            except CheckSubscriptionError:
                if isinstance(self.ui.body, UbuntuAdvantageView):
                    self.ui.body.show_unknown_error()
            else:
                if isinstance(self.ui.body, UbuntuAdvantageView):
                    self.ui.body.show_activable_services(svcs)

        self._check_task = schedule_task(inner())

    def cancel_check_token(self) -> None:
        """ Cancel the asynchronous token check (if started). """
        if self._check_task is not None:
            self._check_task.cancel()

    def cancel(self) -> None:
        self.app.prev_screen()

    def done(self, token: str) -> None:
        log.debug("UbuntuAdvantageController.done token=%s", token)
        self.app.next_screen(
            self.endpoint.POST(UbuntuAdvantageInfo(token=token))
        )
