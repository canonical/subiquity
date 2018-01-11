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
import fcntl
import logging
import os
import struct
import sys
import termios
import tty

import urwid
import yaml

from subiquitycore.signals import Signal
from subiquitycore.prober import Prober, ProberException

log = logging.getLogger('subiquitycore.core')


class ApplicationError(Exception):
    """ Basecontroller exception """
    pass

# From uapi/linux/kd.h:
KDGKBTYPE = 0x4B33  # get keyboard type

GIO_CMAP  = 0x4B70	# gets colour palette on VGA+
PIO_CMAP  = 0x4B71	# sets colour palette on VGA+
UO_R, UO_G, UO_B = 0xe9, 0x54, 0x20

K_RAW       = 0x00
K_XLATE     = 0x01
K_MEDIUMRAW = 0x02
K_UNICODE   = 0x03
K_OFF       = 0x04

KDGKBMODE = 0x4B44 # gets current keyboard mode
KDSKBMODE = 0x4B45 # sets current keyboard mode


class ISO_8613_3_Screen(urwid.raw_display.Screen):

    def __init__(self, _urwid_name_to_rgb):
        self._fg_to_rgb = _urwid_name_to_rgb.copy()
        self._fg_to_rgb['default'] = _urwid_name_to_rgb['light gray']
        self._bg_to_rgb = _urwid_name_to_rgb.copy()
        self._bg_to_rgb['default'] = _urwid_name_to_rgb['black']
        super().__init__()

    def _attrspec_to_escape(self, a):
        f_r, f_g, f_b = self._fg_to_rgb[a.foreground]
        b_r, b_g, b_b = self._bg_to_rgb[a.background]
        return "\x1b[38;2;{};{};{};48;2;{};{};{}m".format(f_r, f_g, f_b, b_r, b_g, b_b)


def is_linux_tty():
    try:
        r = fcntl.ioctl(sys.stdout.fileno(), KDGKBTYPE, ' ')
    except IOError as e:
        log.debug("KDGKBTYPE failed %r", e)
        return False
    log.debug("KDGKBTYPE returned %r", r)
    return r == b'\x02'



def setup_screen(colors, styles):
    """Return a palette and screen to be passed to MainLoop.

    colors is a list of exactly 8 tuples (name, (r, g, b))

    styles is a list of tuples (stylename, fg_color, bg_color) where
    fg_color and bg_color are defined in 'colors'
    """
    # The part that makes this "fun" is that urwid insists on referring
    # to the basic colors by their "standard" names but we overwrite
    # these colors to mean different things.  So we convert styles into
    # an urwid palette by mapping the names in colors to the standard
    # name, and then either overwrite the first 8 colors to be the
    # colors from 'colors' (on the linux vt) or use a custom screen
    # class that displays maps the standard color name to the value
    # specified in colors using 24-bit control codes.
    if len(colors) != 8:
        raise Exception("setup_screen must be passed a list of exactly 8 colors")
    urwid_8_names = (
        'black',
        'dark red',
        'dark green',
        'brown',
        'dark blue',
        'dark magenta',
        'dark cyan',
        'light gray',
    )
    urwid_name = dict(zip([c[0] for c in colors], urwid_8_names))

    urwid_palette = []
    for name, fg, bg in styles:
        urwid_palette.append((name, urwid_name[fg], urwid_name[bg]))

    if is_linux_tty():
        curpal = bytearray(16*3)
        fcntl.ioctl(sys.stdout.fileno(), GIO_CMAP, curpal)
        for i in range(8):
            for j in range(3):
                curpal[i*3+j] = colors[i][1][j]
        fcntl.ioctl(sys.stdout.fileno(), PIO_CMAP, curpal)
        return urwid.raw_display.Screen(), urwid_palette
    else:
        _urwid_name_to_rgb = {}
        for i, n in enumerate(urwid_8_names):
            _urwid_name_to_rgb[n] = colors[i][1]
        return ISO_8613_3_Screen(_urwid_name_to_rgb), urwid_palette



class InputFilter:

    def __init__(self, timelimit=10):
        self._timelimit = timelimit
        self.filtering = False
        self._fd = os.open("/proc/self/fd/0", os.O_RDWR)

    def start_filtering(self):
        log.debug("start_filtering")
        self.filtering = True
        o = bytearray(4)
        fcntl.ioctl(self._fd, KDGKBMODE, o)
        self._old_mode = struct.unpack('i', o)[0]
        self._old_settings = termios.tcgetattr(self._fd)
        new_settings = termios.tcgetattr(self._fd)
        new_settings[tty.IFLAG] = 0
        new_settings[tty.LFLAG] = new_settings[tty.LFLAG] & ~(termios.ECHO | termios.ICANON | termios.ISIG)
        new_settings[tty.CC][termios.VMIN] = 0
        new_settings[tty.CC][termios.VTIME] = 0
        termios.tcsetattr(self._fd, termios.TCSAFLUSH, new_settings)
        log.debug("old mode was %s, setting mode to %s", self._old_mode, K_MEDIUMRAW)
        fcntl.ioctl(self._fd, KDSKBMODE, K_MEDIUMRAW)

    def stop_filtering(self):
        log.debug("stop_filtering")
        self.filtering = False
        log.debug("setting mode back to %s", self._old_mode)
        fcntl.ioctl(self._fd, KDSKBMODE, self._old_mode)
        termios.tcsetattr(self._fd, termios.TCSANOW, self._old_settings)

    def filter(self, keys, codes):
        if self.filtering:
            i = 0
            r = []
            n = len(codes)
            while i < len(codes):
                if codes[i] & 0x80:
                    p = 'release '
                else:
                    p = 'press '
                if i + 2 < n and (codes[i] & 0x7f) == 0 and (codes[i + 1] & 0x80) != 0 and (codes[i + 2] & 0x80) != 0:
                    kc = ((codes[i + 1] & 0x7f) << 7) | (codes[i + 2] & 0x7f)
                    i += 3
                else:
                    kc = codes[i] & 0x7f
                    i += 1
                r.append(p + str(kc))
            return r
        else:
            return keys


class DummyInputFilter:

    def __init__(self, timelimit=10):
        self._timelimit = timelimit
        self.filtering = False

    def start_filtering(self):
        self.filtering = True

    def stop_filtering(self):
        self.filtering = False

    def filter(self, keys, codes):
        return keys


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

        answers = {}
        if opts.answers is not None:
            answers = yaml.safe_load(open(opts.answers).read())
            log.debug("Loaded answers %s", answers)
            if not opts.dry_run:
                open('/run/casper-no-prompt', 'w').close()

        if is_linux_tty():
            log.debug("is_linux_tty")
            input_filter = InputFilter()
        else:
            input_filter = DummyInputFilter()
        self.common = {
            "ui": ui,
            "opts": opts,
            "signal": Signal(),
            "prober": prober,
            "loop": None,
            "pool": futures.ThreadPoolExecutor(1),
            "answers": answers,
            "input_filter": input_filter,
        }
        if opts.screens:
            self.controllers = [c for c in self.controllers if c in opts.screens]
        ui.progress_completion = len(self.controllers)
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
        self.common['ui'].progress_current += 1
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
        self.common['ui'].progress_current -= 1
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

    def run(self):
        if not hasattr(self, 'loop'):
            if self.common['opts'].run_on_serial:
                palette = self.STYLES_MONO
                screen = urwid.raw_display.Screen()
            else:
                screen, palette = setup_screen(self.COLORS, self.STYLES)

            self.common['loop'] = urwid.MainLoop(
                self.common['ui'], palette=palette, screen=screen,
                handle_mouse=False, pop_ups=True, input_filter=self.common['input_filter'].filter)

            log.debug("Running event loop: {}".format(
                self.common['loop'].event_loop))
            self.common['input_filter']._loop = self.common['loop']
            self.common['base_model'] = self.model_class(self.common)

        try:
            self.common['loop'].set_alarm_in(0.05, self.next_screen)
            controllers_mod = __import__('%s.controllers' % self.project, None, None, [''])
            for k in self.controllers:
                log.debug("Importing controller: {}".format(k))
                klass = getattr(controllers_mod, k+"Controller")
                self.common['controllers'][k] = klass(self.common)
            log.debug("*** %s", self.common['controllers'])
            self._connect_base_signals()
            self.common['loop'].run()
        except:
            log.exception("Exception in controller.run():")
            raise
