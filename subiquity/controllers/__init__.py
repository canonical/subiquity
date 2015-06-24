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
import urwid
from subiquity.routes import Routes


log = logging.getLogger('subiquity.controller')


class BaseControllerError(Exception):
    """ Basecontroller exception """
    pass


class BaseController:
    def __init__(self, ui, palette, opts):
        self.ui = ui
        self.palette = palette
        self.opts = opts

    def next_controller(self, *args, **kwds):
        controller = Routes.next()
        controller(self).show(*args, **kwds)

    def prev_controller(self, *args, **kwds):
        controller = Routes.prev()
        controller(self).show(*args, **kwds)

    def redraw_screen(self):
        try:
            self.loop.draw_screen()
        except AssertionError as e:
            log.exception("exception failure in redraw_screen")
            raise e

    def set_alarm_in(self, interval, cb):
        self.loop.set_alarm_in(interval, cb)
        return

    def header_hotkeys(self, key):
        if key in ['q', 'Q']:
            raise urwid.ExitMainLoop()

    def set_body(self, w):
        self.ui.set_body(w)
        self.redraw_screen()

    def set_header(self, title, excerpt):
        self.ui.set_header(title, excerpt)
        self.redraw_screen()

    def set_footer(self, message):
        self.ui.set_footer(message)
        self.redraw_screen()

    def run(self):
        self.main_loop()

    def main_loop(self):
        """ Run eventloop
        """
        self.loop = urwid.MainLoop(self.ui, self.palette,
                                   unhandled_input=self.header_hotkeys)

        try:
            self.loop.run()
        except:
            log.exception("Exception in controller.run():")
            raise
        Routes.reset()
        initial_controller = Routes.first()
        self.set_body(initial_controller(self).show())
