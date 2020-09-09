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

from abc import ABC
import logging

log = logging.getLogger("subiquitycore.controller")


class BaseController(ABC):
    """Base class for controllers."""

    signals = []
    model_name = None

    def __init__(self, app):
        self.name = type(self).__name__[:-len("Controller")]
        self.signal = app.signal
        self.opts = app.opts
        self.app = app
        self.context = self.app.context.child(self.name, childlevel="DEBUG")
        if self.model_name is not None:
            self.model = getattr(self.app.base_model, self.model_name)

    def register_signals(self):
        """Defines signals associated with controller from model."""
        signals = []
        for sig, cb in self.signals:
            signals.append((sig, getattr(self, cb)))
        self.signal.connect_signals(signals)

    def start(self):
        """Called just before the main loop is started.

        At the time this is called, all controllers and models and so on
        have been created. This is when the controller should start
        interacting with the outside world, e.g. probing for network
        devices or start making connections to the snap store.
        """
        pass

    def serialize(self):
        return None

    def deserialize(self, data):
        if data is not None:
            raise Exception("missing deserialize method on {}".format(self))
