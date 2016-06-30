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
from tornado.ioloop import IOLoop
from tornado.util import import_object
from subiquitycore.signals import Signal
from subiquitycore.palette import STYLES, STYLES_MONO
from subiquitycore.prober import Prober, ProberException

from subiquitycore.core import CoreControllerError, Controller as ControllerBase

log = logging.getLogger('console_conf.core')


class CoreControllerError(Exception):
    """ Basecontroller exception """
    pass


class Controller(ControllerBase):
    def __init__(self, ui, opts):
        try:
            prober = Prober(opts)
        except ProberException as e:
            err = "Prober init failed: {}".format(e)
            log.exception(err)
            raise CoreControllerError(err)

        self.common = {
            "ui": ui,
            "opts": opts,
            "signal": Signal(),
            "prober": prober,
            "loop": None
        }
        self.controllers = {
            "Welcome": None,
            "Network": None,
            "Identity": None,
            "Login": None,
        }
        self.common['controllers'] = self.controllers

    def run(self):
        if not hasattr(self, 'loop'):
            palette = STYLES
            additional_opts = {
                'screen': urwid.raw_display.Screen(),
                'unhandled_input': self.header_hotkeys,
                'handle_mouse': False
            }
            if self.common['opts'].run_on_serial:
                palette = STYLES_MONO
            else:
                additional_opts['screen'].set_terminal_properties(colors=256)
                additional_opts['screen'].reset_default_terminal_palette()

            evl = urwid.TornadoEventLoop(IOLoop())
            self.common['loop'] = urwid.MainLoop(
                self.common['ui'], palette, event_loop=evl, **additional_opts)
            log.debug("Running event loop: {}".format(
                self.common['loop'].event_loop))

        try:
            self.set_alarm_in(0.05, self.welcome)
            for k in self.controllers.keys():
                log.debug("Importing controller: {}".format(k))
                klass = import_object(
                    "subiquitycore.controllers.{}Controller".format(
                        k))
                klass = import_object(
                    "console_conf.controllers.{}Controller".format(
                        k))
                self.controllers[k] = klass(self.common)

            self._connect_base_signals()
            self.common['loop'].run()
        except:
            log.exception("Exception in controller.run():")
            raise
