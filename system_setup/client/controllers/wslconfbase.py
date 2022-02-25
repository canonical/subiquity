import logging

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import WSLConfigurationBase
from system_setup.ui.views.wslconfbase import WSLConfigurationBaseView

log = logging.getLogger('system_setup.client.controllers.wslconfbase')


class WSLConfigurationBaseController(SubiquityTuiController):
    endpoint_name = 'wslconfbase'

    async def make_ui(self):
        data = await self.endpoint.GET()
        return WSLConfigurationBaseView(self, data)

    def run_answers(self):
        if all(elem in self.answers for elem in
               ['automount_root', 'automount_options',
                'network_generatehosts', 'network_generateresolvconf']):
            configuration = WSLConfigurationBase(**self.answers)
            self.done(configuration)

    def done(self, configuration_data):
        log.debug(
            "WSLConfigurationBaseController.done next_screen user_spec=%s",
            configuration_data)
        self.app.next_screen(self.endpoint.POST(configuration_data))

    def cancel(self):
        self.app.prev_screen()
