import os
import pwd
import aiohttp
import asyncio
import logging

from subiquitycore.context import with_context

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import (
    ApplicationState,
    ShutdownMode
    )
from subiquity.ui.views.installprogress import (
    InstallRunning,
    )

from system_setup.ui.views.summary import SummaryView


log = logging.getLogger('ubuntu_wsl_oobe.controllers.summary')


class SummaryController(SubiquityTuiController):

    def __init__(self, app):
        super().__init__(app)
        self.app_state = None
        self.crash_report_ref = None
        self.summary_view = None

    def start(self):
        self.app.aio_loop.create_task(self._wait_status())

    def cancel(self):
        self.app.cancel()

    def run_answers(self):
        pass

    def click_reboot(self):
        self.app.aio_loop.create_task(self.send_reboot_and_wait())

    async def send_reboot_and_wait(self):
        try:
            await self.app.client.shutdown.POST(mode=ShutdownMode.REBOOT)
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

            if self.summary_view:
                self.summary_view.update_for_state(self.app_state)
            if app_status.error is not None:
                if self.crash_report_ref is None:
                    self.crash_report_ref = app_status.error
                    if self.summary_view:
                        self.ui.set_body(self.summary_view)
                    self.app.show_error_report(self.crash_report_ref)

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

    async def make_ui(self):
        real_name = ""

        tmp_variant = "wsl_setup"
        onsite_variant = getattr(self.app, "variant")
        if onsite_variant is not None:
            tmp_variant = onsite_variant

        identity = getattr(self.app.client, "identity")
        if identity is not None:
            data = await identity.GET()
            real_name = data.realname
        if tmp_variant == "wsl_configuration":
            tmp_uid = os.getuid()
            if tmp_uid >= 1000 and tmp_uid < 65534:
                real_name = pwd.getpwuid(tmp_uid)[0]

        self.summary_view = SummaryView(self, real_name)
        # We may reach the DONE or ERROR state even before we had a chance
        # to show the UI.
        self.summary_view.update_for_state(self.app_state)
        return self.summary_view
