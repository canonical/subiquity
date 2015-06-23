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
from subiquity.routes import Routes


class ApplicationError(Exception):
    """ Exception in Application Class """
    pass


class Application:
    def __init__(self, screen, opts):
        self.screen = screen
        self.opts = opts
        self.welcome_controller = Routes.first()

        # Setup eventloop
        self.loop = self._build_loop()
        self.loop.set_alarm_in(2, self.update)

    def _build_loop(self):
        """ Builds urwid eventloop, passing in itself to the controllers
        for further display manipulation
        """
        return urwid.MainLoop(self.welcome_controller(routes=Routes,
                                                      application=self).show(),
                              screen=self.screen,
                              unhandled_input=self.unhandled_input)

    def unhandled_input(self, key):
        if key in ('Q', 'q', 'esc'):
            raise urwid.ExitMainLoop()
        if key in ('r', 'R'):
            self.redraw_screen()

    def redraw_screen(self):
        try:
            self.loop.draw_screen()
        except AssertionError as e:
            # self.log.exception("exception failure in redraw_screen")
            raise e

    def set_alarm_in(self, interval, cb):
        self.loop.set_alarm_in(interval, cb)

    def update(self, *args, **kwds):
        if self.loop is not None:
            self.redraw_screen()
            self.set_alarm_in(1, self.update)

    def start(self):
        try:
            self.loop.run()
        except:
            raise ApplicationError("Exception in loop.run()")
