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
from abc import ABC
from typing import Optional

log = logging.getLogger("subiquitycore.controller")


class BaseController(ABC):
    """Base class for controllers."""

    model_name: Optional[str] = None

    def __init__(self, app):
        self.name = type(self).__name__[: -len("Controller")]
        self.opts = app.opts
        self.app = app
        self.context = self.app.context.child(self.name, childlevel="DEBUG")
        if self.model_name is not None:
            # Model names are used as the target of saying something is
            # configured, but sometimes there isn't actually a model.
            self.model = getattr(self.app.base_model, self.model_name, None)

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
