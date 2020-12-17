# Copyright 2015 Canonical, Ltd.
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

import aiohttp

from subiquitycore.context import with_context

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import ApplicationState
from subiquity.ui.views.installprogress import (
    InstallRunning,
    ProgressView,
    )


log = logging.getLogger("subiquity.client.controllers.progress")


class ProgressController(SubiquityTuiController):

    def __init__(self, app):
        super().__init__(app)
        self.progress_view = ProgressView(self)
        self.app_state = None
        self.crash_report_ref = None
        self.answers = app.answers.get("InstallProgress", {})

    def event(self, event):
        if event["SUBIQUITY_EVENT_TYPE"] == "start":
            self.progress_view.event_start(
                event["SUBIQUITY_CONTEXT_ID"],
                event.get("SUBIQUITY_CONTEXT_PARENT_ID"),
                event["MESSAGE"])
        elif event["SUBIQUITY_EVENT_TYPE"] == "finish":
            self.progress_view.event_finish(
                event["SUBIQUITY_CONTEXT_ID"])

    def log_line(self, event):
        log_line = event['MESSAGE']
        self.progress_view.add_log_line(log_line)

    def cancel(self):
        pass

    def start(self):
        self.app.aio_loop.create_task(self._wait_status())

    def click_reboot(self):
        self.app.aio_loop.create_task(self.send_reboot_and_wait())

    async def send_reboot_and_wait(self):
        try:
            await self.app.client.reboot.POST()
        except aiohttp.ClientError:
            pass
        self.app.exit()

    @with_context()
    async def _wait_status(self, context):
        install_running = None
        while True:
            try:
                app_status = await self.app.client.meta.status.GET(
                    cur=self.app_state)
            except aiohttp.ClientError:
                await asyncio.sleep(1)
                continue
            self.app_state = app_status.state

            self.progress_view.update_for_state(self.app_state)
            if self.ui.body is self.progress_view:
                self.ui.set_header(self.progress_view.title)

            if app_status.error is not None:
                if self.crash_report_ref is None:
                    self.crash_report_ref = app_status.error
                    self.ui.set_body(self.progress_view)
                    self.app.show_error_report(self.crash_report_ref)

            if self.app_state == ApplicationState.NEEDS_CONFIRMATION:
                if self.showing:
                    self.app.show_confirm_install()

            if self.app_state == ApplicationState.RUNNING:
                if app_status.confirming_tty != self.app.our_tty:
                    install_running = InstallRunning(
                        self.app, app_status.confirming_tty)
                    self.app.add_global_overlay(install_running)
            else:
                if install_running is not None:
                    self.app.remove_global_overlay(install_running)
                    install_running = None

            if self.app_state == ApplicationState.DONE:
                if self.answers.get('reboot', False):
                    self.click_reboot()

    def make_ui(self):
        if self.app_state == ApplicationState.NEEDS_CONFIRMATION:
            self.app.show_confirm_install()
        return self.progress_view

    def run_answers(self):
        pass
