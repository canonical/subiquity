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
import urwid.curses_display
from subiquity.routes import Routes
from subiquity.palette import STYLES, STYLES_MONO


log = logging.getLogger('subiquity.controller')


class BaseControllerError(Exception):
    """ Basecontroller exception """
    pass


class BaseController:
    def __init__(self, ui, opts):
        self.ui = ui
        self.opts = opts

    def next_controller(self, *args, **kwds):
        controller = Routes.next()
        controller(self).show(*args, **kwds)

    def prev_controller(self, *args, **kwds):
        controller = Routes.prev()
        controller(self).show(*args, **kwds)

    def redraw_screen(self):
        if hasattr(self, 'loop'):
            try:
                self.loop.draw_screen()
            except AssertionError as e:
                log.critical(e)

    def set_alarm_in(self, interval, cb):
        self.loop.set_alarm_in(interval, cb)
        return

    def update(self, *args, **kwds):
        route = Routes.current_idx()
        if route == 0:
            self.begin()
        self.set_alarm_in(1, self.update)

    def exit(self):
        raise urwid.ExitMainLoop()

    def header_hotkeys(self, key):
        if key in ['q', 'Q']:
            self.exit()

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
        if not hasattr(self, 'loop'):
            if self.opts.run_on_serial:
                screen = urwid.raw_display.Screen()
                screen.register_palette(STYLES_MONO)
            else:
                screen = urwid.raw_display.Screen()
                screen.set_mouse_tracking(False)
                screen.set_terminal_properties(256)
                screen.register_palette(STYLES)

            self.loop = urwid.MainLoop(self.ui, screen=screen,
                                       unhandled_input=self.header_hotkeys)

        try:
            self.begin()
            self.loop.run()
        except:
            log.exception("Exception in controller.run():")
            raise

    def begin(self):
        """ Initializes the first controller for installation """
        Routes.reset()
        initial_controller = Routes.first()
        initial_controller(self).show()
