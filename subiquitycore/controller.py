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

log = logging.getLogger("subiquitycore.controller")


class BaseController:
    """Base class for controllers."""

    def __init__(self, common):
        self.ui = common['ui']
        self.signal = common['signal']
        self.opts = common['opts']
        self.loop = common['loop']
        self.prober = common['prober']
        self.controllers = common['controllers']

    def register_signals(self):
        """Defines signals associated with controller from model."""
        if hasattr(self, 'model'):
            signals = []
            for name, sig, cb in self.model.get_signals():
                signals.append((sig, getattr(self, cb)))
            self.signal.connect_signals(signals)
        else:
            log.debug("No model signals found for {}".format(self))
