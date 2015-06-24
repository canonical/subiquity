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

""" Controller policy """

from abc import ABCMeta, abstractmethod


class ControllerPolicy(metaclass=ABCMeta):

    def __init__(self, ui):
        self.ui = ui

    @abstractmethod
    def show(self, *args, **kwds):
        """ Implements show action for the controller

        Renders the View for controller.
        """
        pass

    @abstractmethod
    def finish(self):
        """ Implements finish action for controller.

        This handles any callback data/procedures required
        to move to the next controller or end the install.
        """
        pass
