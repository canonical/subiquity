# Copyright 2015 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging

from console_conf.models.console_conf import ConsoleConfModel
from console_conf.models.systems import RecoverySystemsModel
from subiquitycore.prober import Prober
from subiquitycore.snap import snap_name
from subiquitycore.snapd import SnapdConnection
from subiquitycore.tui import TuiApplication

log = logging.getLogger("console_conf.core")

# project is used to build the state directory path under /run/, which usually
# ends up as /run/console-conf. Note this should only be changed in
# coordination with console-conf-wrapper and any other glue shipped with Ubuntu
# Core boot base
CONSOLE_CONF_PROJECT = snap_name() or "console-conf"


class ConsoleConf(TuiApplication):
    from console_conf import controllers as controllers_mod

    project = CONSOLE_CONF_PROJECT

    make_model = ConsoleConfModel

    controllers = [
        "Welcome",
        "Network",
        "Identity",
    ]

    def __init__(self, opts):
        super().__init__(opts)
        self.prober = Prober(opts.machine_config, self.debug_flags)
        # we're talking to snapd over the main socket, this may require
        # snapd-control if executing inside a snap
        self.snapdcon = SnapdConnection(self.root, "/run/snapd.socket")


class RecoveryChooser(TuiApplication):
    from console_conf import controllers as controllers_mod

    project = CONSOLE_CONF_PROJECT

    controllers = [
        "RecoveryChooserWelcome",
        "RecoveryChooser",
        "RecoveryChooserConfirm",
    ]

    def __init__(self, opts, chooser_input, chooser_output):
        """Takes the options and raw input/output streams for communicating
        with the chooser parent process.
        """
        self._chooser_output = chooser_output
        # make_model is used by super()'s constructor, but we need to use the
        # instance data
        self.make_model = lambda: RecoverySystemsModel.from_systems_stream(
            chooser_input
        )

        super().__init__(opts)
        self.prober = Prober(opts.machine_config, self.debug_flags)

    def respond(self, choice):
        """Produce a response to the parent process"""
        self.base_model.to_response_stream(choice, self._chooser_output)
