import logging

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import WSLConfiguration1Data
from system_setup.ui.views.integration import IntegrationView

log = logging.getLogger('ubuntu_wsl_oobe.controllers.integration')


class IntegrationController(SubiquityTuiController):
    endpoint_name = 'wslconf1'

    async def make_ui(self):
        data = await self.endpoint.GET()
        return IntegrationView(self, data)

    def run_answers(self):
        if all(elem in self.answers for elem in
               ['custom_path', 'custom_mount_opt', 'gen_host', 'gen_resolvconf']):
            integration = WSLConfiguration1Data(
                custom_path=self.answers['custom_path'],
                custom_mount_opt=self.answers['custom_mount_opt'],
                gen_host=self.answers['gen_host'],
                gen_resolvconf=self.answers['gen_resolvconf'])
            self.done(integration)

    def done(self, integration_data):
        log.debug(
            "IntegrationController.done next_screen user_spec=%s",
            integration_data)
        self.app.next_screen(self.endpoint.POST(integration_data))

    def cancel(self):
        self.app.prev_screen()
