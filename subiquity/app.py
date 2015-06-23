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

""" Application entry point """

import urwid
import logging
from subiquity.routes import Routes
from subiquity.ui.frame import SubiquityUI

log = logging.getLogger('subiquity.app')


class ApplicationError(Exception):
    """ Exception in Application Class """
    pass


class Application:
    def __init__(self, screen, opts):
        self.screen = screen
        self.opts = opts
        self.routes = Routes
        self.ui = SubiquityUI()
        self.loop = None

    def unhandled_input(self, key):
        if key in ('Q', 'q', 'esc'):
            raise urwid.ExitMainLoop()
        if key in ('r', 'R'):
            self.loop.draw_screen()

    def start(self):
        try:
            self.loop = urwid.MainLoop(self.ui,
                                       screen=self.screen,
                                       unhandled_input=self.unhandled_input)

            self.loop.run()
        except:
            raise ApplicationError("Exception in loop.run()")
        return self.initialize()

    def initialize(self):
        # Build common dictionary for use throughout application
        common = dict(opts=self.opts,
                      routes=self.routes,
                      ui=self.ui,
                      loop=self.loop)
        # Setup first controller
        controller = Routes.first()
        return controller(common).show()
