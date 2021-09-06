import logging

from subiquity.client.controller import SubiquityTuiController
from subiquity.common.types import WSLConfigurationBase
from system_setup.ui.views.wslconfbase import WSLConfigurationBaseView

log = logging.getLogger('system_setup.client.controllers.wslconfigurationbase')


class WSLConfigurationBaseController(SubiquityTuiController):
    endpoint_name = 'wslconfbase'

    async def make_ui(self):
        data = await self.endpoint.GET()
        variant = "wsl_setup"
        onsite_variant = getattr(self.app, "variant")
        if onsite_variant is not None:
            variant = onsite_variant
        return WSLConfigurationBaseView(self, data, variant)

    def run_answers(self):
        if all(elem in self.answers for elem in
               ['custom_path', 'custom_mount_opt',
                'gen_host', 'gen_resolvconf']):
            configuration = WSLConfigurationBase(
                custom_path=self.answers['custom_path'],
                custom_mount_opt=self.answers['custom_mount_opt'],
                gen_host=self.answers['gen_host'],
                gen_resolvconf=self.answers['gen_resolvconf'])
            self.done(configuration)

    def done(self, configuration_data):
        log.debug(
            "WSLConfigurationBaseController.done next_screen user_spec=%s",
            configuration_data)
        self.app.next_screen(self.endpoint.POST(configuration_data))

    def cancel(self):
        self.app.prev_screen()
