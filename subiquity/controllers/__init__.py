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

from abc import ABCMeta, abstractmethod
from importlib import import_module
import pkgutil


class BaseController(metaclass=ABCMeta):
    controller_name = None

    @classmethod
    def name(cls):
        if cls.controller_name:
            return cls.controller_name
        return cls.__name__.lower()

    @abstractmethod
    def show(self):
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

    def next_controller(self, name, *args):
        """ Loads next controller and associated View

        :param str name: Name of next controller
        :param list args: List of arguments for next controller to use.
        """
        controller = import_module('subiquity.controllers.' + name)
        controller.__controller_class__().show(*args)

    def prev_controller(self, name, *args):
        """ Loads previous controller and associated View

        :param str name: Name of previous controller
        :param list args: List of arguments for previous controller to use.
        """
        controller = import_module('subiquity.controllers.' + name)
        controller.__controller_class__().show(*args)
