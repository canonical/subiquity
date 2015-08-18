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
from subiquity.signals import Signal
from subiquity.palette import STYLES, STYLES_MONO

# Modes import ----------------------------------------------------------------
from subiquity.controllers import (WelcomeController,
                                   InstallpathController,
                                   NetworkController,
                                   FilesystemController,
                                   InstallProgressController)

log = logging.getLogger('subiquity.core')


class CoreControllerError(Exception):
    """ Basecontroller exception """
    pass


class Controller:
    def __init__(self, ui, opts):
        self.ui = ui
        self.opts = opts
        self.signal = Signal()
        self.controllers = {
            "welcome": WelcomeController(self.ui, self.signal),
            "installpath": InstallpathController(self.ui, self.signal),
            "network": NetworkController(self.ui, self.signal),
            "filesystem": FilesystemController(self.ui, self.signal),
            "progress": InstallProgressController(self.ui, self.signal),
        }
        self._connect_base_signals()

    def _connect_base_signals(self):
        """ Connect signals used in the core controller
        """
        signals = []

        # Add quit signal
        signals.append(('quit', self.exit))
        self.signal.connect_signals(signals)

        # Registers signals from each controller
        for controller, controller_class in self.controllers.items():
            controller_class.register_signals()
        log.debug(self.signal)

# EventLoop -------------------------------------------------------------------
    def redraw_screen(self):
        if hasattr(self, 'loop'):
            try:
                self.loop.draw_screen()
            except AssertionError as e:
                log.critical("Redraw screen error: {}".format(e))

    def set_alarm_in(self, interval, cb):
        self.loop.set_alarm_in(interval, cb)
        return

    def update(self, *args, **kwds):
        """ Update loop """
        pass

    def exit(self):
        raise urwid.ExitMainLoop()

    def header_hotkeys(self, key):
        if key in ['q', 'Q', 'ctrl c']:
            self.exit()

    def run(self):
        if not hasattr(self, 'loop'):
            palette = STYLES
            additional_opts = {
                'screen': urwid.raw_display.Screen(),
                'unhandled_input': self.header_hotkeys,
                'handle_mouse': False
            }
            if self.opts.run_on_serial:
                palette = STYLES_MONO
                additional_opts['screen'] = urwid.curses_display.Screen()
            else:
                additional_opts['screen'].set_terminal_properties(colors=256)
                additional_opts['screen'].reset_default_terminal_palette()

            self.loop = urwid.MainLoop(
                self.ui, palette, **additional_opts)

        try:
            self.set_alarm_in(0.05, self.welcome)
            # self.install_progress_fd = self.loop.watch_pipe(
            #     self.install_progress_status)
            self.loop.run()
        except:
            log.exception("Exception in controller.run():")
            raise

    # Welcome Mode ------------------------------------------------------------
    #
    # Starts the initial UI view.
    def welcome(self, *args, **kwargs):
        self.controllers['welcome'].welcome()
