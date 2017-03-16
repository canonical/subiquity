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

from concurrent import futures
import logging

import urwid

from subiquitycore.signals import Signal
from subiquitycore.palette import STYLES, STYLES_MONO
from subiquitycore.prober import Prober, ProberException

log = logging.getLogger('subiquitycore.core')


class ApplicationError(Exception):
    """ Basecontroller exception """
    pass


class Application:

    # A concrete subclass must set project and controllers attributes, e.g.:
    #
    # project = "subiquity"
    # controllers = [
    #         "Welcome",
    #         "Installpath",
    #         "Network",
    #         "Filesystem",
    #         "Identity",
    #         "InstallProgress",
    #         "Login",
    # ]
    # The 'next-screen' and 'prev-screen' signals move through the list of
    # controllers in order, calling the default method on the controller
    # instance.

    def __init__(self, ui, opts):
        try:
            prober = Prober(opts)
        except ProberException as e:
            err = "Prober init failed: {}".format(e)
            log.exception(err)
            raise ApplicationError(err)

        opts.project = self.project

        self.common = {
            "ui": ui,
            "opts": opts,
            "signal": Signal(),
            "prober": prober,
            "loop": None,
            "pool": futures.ThreadPoolExecutor(1),
        }
        self.common['controllers'] = dict.fromkeys(self.controllers)
        self.controller_index = -1

    def _connect_base_signals(self):
        """ Connect signals used in the core controller
        """
        signals = []

        signals.append(('quit', self.exit))
        if self.common['opts'].dry_run:
            signals.append(('control-x-quit', self.exit))
        signals.append(('refresh', self.redraw_screen))
        signals.append(('next-screen', self.next_screen))
        signals.append(('prev-screen', self.prev_screen))
        self.common['signal'].connect_signals(signals)

        # Registers signals from each controller
        for controller, controller_class in self.common['controllers'].items():
            controller_class.register_signals()
        log.debug(self.common['signal'])

    def next_screen(self, *args):
        self.controller_index += 1
        if self.controller_index >= len(self.controllers):
            self.exit()
        controller_name = self.controllers[self.controller_index]
        log.debug("moving to screen %s", controller_name)
        next_controller = self.common['controllers'][controller_name]
        next_controller.default()

    def prev_screen(self, *args):
        if self.controller_index == 0:
            return
        self.controller_index -= 1
        if self.controller_index >= len(self.controllers):
            self.exit()
        controller_name = self.controllers[self.controller_index]
        next_controller = self.common['controllers'][controller_name]
        next_controller.default()

# EventLoop -------------------------------------------------------------------
    def redraw_screen(self):
        if self.common['loop'] is not None:
            try:
                self.common['loop'].draw_screen()
            except AssertionError as e:
                log.critical("Redraw screen error: {}".format(e))

    def exit(self):
        raise urwid.ExitMainLoop()

    def header_hotkeys(self, key):
        return False

    def run(self):
        if not hasattr(self, 'loop'):
            palette = STYLES
            additional_opts = {
                'screen': urwid.raw_display.Screen(),
                'unhandled_input': self.header_hotkeys,
                'handle_mouse': False,
                'pop_ups': True,
            }
            if self.common['opts'].run_on_serial:
                palette = STYLES_MONO
            else:
                additional_opts['screen'].set_terminal_properties(colors=256)
                additional_opts['screen'].reset_default_terminal_palette()

            self.common['loop'] = urwid.MainLoop(
                self.common['ui'], palette, **additional_opts)
            log.debug("Running event loop: {}".format(
                self.common['loop'].event_loop))

        try:
            self.common['loop'].set_alarm_in(0.05, self.next_screen)
            controllers_mod = __import__('%s.controllers' % self.project, None, None, [''])
            for k in self.common['controllers']:
                log.debug("Importing controller: {}".format(k))
                klass = getattr(controllers_mod, k+"Controller")
                self.common['controllers'][k] = klass(self.common)
            log.debug("*** %s", self.common['controllers'])
            self._connect_base_signals()
            self.common['loop'].run()
        except:
            log.exception("Exception in controller.run():")
            raise
