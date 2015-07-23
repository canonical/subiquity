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

""" Model Policy
"""

from abc import ABC, abstractmethod


class ModelPolicyException(Exception):
    "Problem in model policy"


class ModelPolicy(ABC):
    """ Expected contract for defining models
    """
    # Exposed emitter signals
    signals = []

    # Back navigation
    prev_signal = None

    @abstractmethod
    def get_signal_by_name(self, *args, **kwargs):
        """ Implements a getter for retrieving
        signals exposed by the model
        """
        pass

    @abstractmethod
    def get_signals(self):
        """ Lists available signals for model

        Should return a list with a tuple format of
        [('Name of item', 'signal-name', 'callback function string')]
        """
        pass

    @abstractmethod
    def get_menu(self):
        """ Returns a list of menu items

        Should return a list with a tuple format the same
        as get_signals()
        """
        pass

    @property
    def get_previous_signal(self):
        """ Returns the previous defined signal
        """
        if self.prev_signal is None:
            return 'welcome:show'
        name, signal, cb = self.prev_signal
        return signal
