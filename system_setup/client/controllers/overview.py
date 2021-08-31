import logging
from subiquity.client.controller import SubiquityTuiController

from system_setup.ui.views.overview import OverviewView

log = logging.getLogger('ubuntu_wsl_oobe.controllers.overview')


class OverviewController(SubiquityTuiController):

    async def make_ui(self):
        return OverviewView(self)

    def cancel(self):
        self.app.cancel()

    def run_answers(self):
        self.done(None)

    def done(self, result):
        log.debug(
            "OverviewController.done next_screen")
        self.app.next_screen()
