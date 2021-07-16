import logging
from subiquity.client.controller import SubiquityTuiController

from subiquitycore.utils import run_command
from system_setup.ui.views.overview import OverviewView

log = logging.getLogger('ubuntu_wsl_oobe.controllers.identity')


def disable_ubuntu_wsl_oobe():
    """ Stop running ubuntu_wsl_oobe and remove the package """
    log.info('disabling ubuntu-wsl-oobe service')
    #run_command(["apt", "remove", "-y", "ubuntu-wsl-oobe", "ubuntu-wsl-oobe-subiquitycore"])
    return


class OverviewController(SubiquityTuiController):

    async def make_ui(self):
        return OverviewView(self)

    def cancel(self):
        self.app.cancel()

    def done(self, result):
        if not self.opts.dry_run:
            disable_ubuntu_wsl_oobe()
        self.app.exit()
