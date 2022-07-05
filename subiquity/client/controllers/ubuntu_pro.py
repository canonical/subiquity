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

from urwid import Widget

from subiquitycore.async_helpers import schedule_task

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import (
    UbuntuProInfo,
    UbuntuProCheckTokenStatus as TokenStatus,
    UbuntuProService,
    )
from subiquity.ui.views.ubuntu_pro import (
    UbuntuProView,
    UpgradeYesNoForm,
    UpgradeModeForm,
    TokenAddedWidget,
    )

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
        if "LTS" not in lsb["description"]:
            await self.endpoint.skip.POST()
            raise Skip("Not running LTS version")

        ubuntu_pro_info = await self.endpoint.GET()
        return UbuntuProView(self, ubuntu_pro_info.token)

    async def run_answers(self) -> None:
        """ Interact with the UI to go through the pre-attach process if
        requested. """
        if "token" not in self.answers:
            return

        from subiquitycore.testing.view_helpers import (
            click,
            enter_data,
            find_button_matching,
            find_with_pred,
            keypress,
        )

        view = self.app.ui.body

        def run_yes_no_screen(skip: bool) -> None:
            if skip:
                radio = view.upgrade_yes_no_form.skip.widget
            else:
                radio = view.upgrade_yes_no_form.upgrade.widget

            keypress(radio, key="enter")
            click(find_button_matching(view, UpgradeYesNoForm.ok_label))

        def run_token_screen(token: str) -> None:
            keypress(view.upgrade_mode_form.with_contract_token.widget,
                     key="enter")
            data = {"with_contract_token_subform": {"token": token}}
            # TODO: add this point, it would be good to trigger the validation
            # code for the token field.
            enter_data(view.upgrade_mode_form, data)
            click(find_button_matching(view, UpgradeModeForm.ok_label))

        async def run_token_added_overlay() -> None:
            def is_token_added_overlay(widget: Widget) -> bool:
                try:
                    if widget._text == f" {TokenAddedWidget.title} ":
                        return True
                except AttributeError:
                    return False

            # Wait until the "Token added successfully" overlay is shown.
            while not find_with_pred(view, is_token_added_overlay):
                await asyncio.sleep(.2)

            click(find_button_matching(view, TokenAddedWidget.done_label))

        def run_services_screen() -> None:
            click(find_button_matching(view._w,
                                       UbuntuProView.services_done_label))

        if not self.answers["token"]:
            run_yes_no_screen(skip=True)
            return

        run_yes_no_screen(skip=False)
        run_token_screen(self.answers["token"])
        await run_token_added_overlay()
        run_services_screen()

    def check_token(self, token: str,
                    on_success: Callable[[List[UbuntuProService]], None],
                    on_failure: Callable[[TokenStatus], None],
                    ) -> None:
        """ Asynchronously check the token passed as an argument. """
        async def inner() -> None:
            answer = await self.endpoint.check_token.GET(token)
            if answer.status == TokenStatus.VALID_TOKEN:
                await self.endpoint.POST(UbuntuProInfo(token=token))
                on_success(answer.subscription.services)
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
        """ Submit the token and move on to the next screen. """
        self.app.next_screen(
            self.endpoint.POST(UbuntuProInfo(token=token))
        )

    def next_screen(self) -> None:
        """ Move on to the next screen. Assume the token should not be
        submitted (or has already been submitted). """
        self.app.next_screen()
