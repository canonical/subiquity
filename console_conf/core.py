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

import logging

from subiquitycore.core import Application

from console_conf.models.console_conf import ConsoleConfModel
from console_conf.models.systems import RecoverySystemsModel

log = logging.getLogger("console_conf.core")


class ConsoleConf(Application):

    project = "console_conf"

    make_model = ConsoleConfModel

    controllers = [
        "Welcome",
        "Network",
        "Identity",
    ]


class RecoveryChooser(Application):

    project = "console_conf"

    controllers = [
        "RecoveryChooserWelcome",
        "RecoveryChooser",
        "RecoveryChooserConfirm",
    ]

    def __init__(self, opts, chooser_input, chooser_output):
        """Takes the options and raw input/output streams for communicating with the
        chooser parent process.
        """
        self._chooser_output = chooser_output
        # make_model is used by super()'s constructor, but we need to use the
        # instance data
        self.make_model = lambda: RecoverySystemsModel.from_systems_stream(
            chooser_input
        )

        super().__init__(opts)

    def respond(self, choice):
        """Produce a response to the parent process"""
        self.base_model.to_response_stream(choice, self._chooser_output)
