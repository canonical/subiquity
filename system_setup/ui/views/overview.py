""" Overview

Overview provides user with the overview of all the current settings.

"""


import os
import logging

from subiquitycore.ui.buttons import done_btn
from subiquitycore.ui.utils import button_pile, screen
from subiquitycore.view import BaseView

log = logging.getLogger("ubuntu_wsl_oobe.ui.views.overview")


class OverviewView(BaseView):
    title = _("Setup Complete")

    def __init__(self, controller, real_name):
        self.controller = controller
        complete_text = _("Hi {real_name},\n\n"
                          "You have complete the setup!\n\n"
                          "It is suggested to run the following commands"
                          " to update your Ubuntu to the latest version:"
                          "\n\n\n"
                          "  $ sudo apt update\n  $ sudo apt upgrade\n\n\n"
                          "All settings will take effect after next "
                          "restart of Ubuntu.").format(real_name=real_name)

        super().__init__(
            screen(
                rows=[],
                buttons=button_pile(
                    [done_btn(_("Done"), on_press=self.confirm), ]),
                focus_buttons=True,
                excerpt=complete_text,
            )
        )

    def confirm(self, result):
        self.controller.done(result)
