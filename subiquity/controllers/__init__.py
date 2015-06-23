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
from abc import ABCMeta, abstractmethod


log = logging.getLogger('subiquity.controller')


class BaseControllerError(Exception):
    """ Basecontroller exception """
    pass


class BaseController(metaclass=ABCMeta):
    controller_name = None

    def __init__(self, common):
        self.common = common

    @classmethod
    def name(cls):
        if cls.controller_name:
            return cls.controller_name
        return cls.__name__.lower()

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

    def set_header(self, title, excerpt):
        self.common['ui'].set_header(title, excerpt)
        self.redraw_screen()

    def set_footer(self, message):
        self.common['ui'].set_footer(message)
        self.redraw_screen()

    def set_body(self, widget):
        self.common['ui'].set_body(widget)
        self.redraw_screen()

    def redraw_screen(self):
        try:
            self.common['loop'].draw_screen()
        except AssertionError as e:
            raise BaseControllerError(e)

    def next_controller(self, *args, **kwds):
        controller = self.common['routes'].next()
        controller(self.common).show(*args, **kwds)
        self.redraw_screen()

    def prev_controller(self, *args, **kwds):
        controller = self.common['routes'].prev()
        controller(self.common).show(*args, **kwds)
        self.redraw_screen()
