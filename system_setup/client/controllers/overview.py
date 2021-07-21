import logging
from subiquity.client.controller import SubiquityTuiController

from subiquitycore.utils import run_command
from system_setup.ui.views.overview import OverviewView

log = logging.getLogger('ubuntu_wsl_oobe.controllers.identity')



class OverviewController(SubiquityTuiController):

    async def make_ui(self):
        return OverviewView(self)

    def cancel(self):
        self.app.cancel()

    def done(self, result):
        self.app.next_screen()
