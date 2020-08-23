# Copyright 2020 Canonical, Ltd.
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

import fcntl
import logging
import os
import sys
import tty

import urwid

from subiquitycore.palette import COLORS, urwid_8_names

log = logging.getLogger('subiquitycore.screen')


# From uapi/linux/kd.h:
KDGKBTYPE = 0x4B33  # get keyboard type

GIO_CMAP = 0x4B70  # gets colour palette on VGA+
PIO_CMAP = 0x4B71  # sets colour palette on VGA+
UO_R, UO_G, UO_B = 0xe9, 0x54, 0x20


class SubiquityScreen(urwid.raw_display.Screen):

    # This class fixes a bug in urwid's screen:
    #
    # Calling screen.stop() sends the INPUT_DESCRIPTORS_CHANGED signal. This
    # calls _reset_input_descriptors() which calls unhook_event_loop /
    # hook_event_loop on the screen. But this all happens before _started is
    # set to False on the screen and so this does not actually do anything. If
    # we call stop and then, for example, run bash, we end up attempting to
    # read from stdin while in a background process group and that gets the
    # kernel upset at us.
    #
    # The cleanest fix seems to be to just send the signal again once stop()
    # has returned which, now that screen._started is False, correctly stops
    # listening from stdin.
    #
    # There is an exactly analagous problem with screen.start() except there
    # the symptom is that we are running in the foreground but not listening to
    # stdin! The fix is the same.

    def start(self):
        super().start()
        urwid.emit_signal(self, urwid.display_common.INPUT_DESCRIPTORS_CHANGED)
        # We run the terminal in raw, not cbreak mode.
        fd = self._term_input_file.fileno()
        if os.isatty(fd):
            tty.setraw(fd)

    def stop(self):
        super().stop()
        urwid.emit_signal(self, urwid.display_common.INPUT_DESCRIPTORS_CHANGED)


class LinuxScreen(SubiquityScreen):

    def __init__(self, colors, **kwargs):
        self._colors = colors
        super().__init__(**kwargs)

    def start(self):
        self.curpal = bytearray(16*3)
        fcntl.ioctl(sys.stdout.fileno(), GIO_CMAP, self.curpal)
        newpal = self.curpal.copy()
        for i in range(8):
            for j in range(3):
                newpal[i*3+j] = self._colors[i][1][j]
        fcntl.ioctl(self._term_input_file.fileno(), PIO_CMAP, newpal)
        super().start()

    def stop(self):
        fcntl.ioctl(self._term_input_file.fileno(), PIO_CMAP, self.curpal)
        super().stop()


class TwentyFourBitScreen(SubiquityScreen):

    def __init__(self, colors, **kwargs):
        self._urwid_name_to_rgb = {
            n: colors[i][1] for i, n in enumerate(urwid_8_names)}
        super().__init__(**kwargs)

    def _cc(self, color):
        """Return the "SGR" parameter for selecting color.

        See https://en.wikipedia.org/wiki/ANSI_escape_code#SGR for an
        explanation.  We use the basic codes for black/white/default for
        maximum compatibility; they are the only colors used when the
        mono palette is selected.
        """
        if color == 'white':
            return '7'
        elif color == 'black':
            return '0'
        elif color == 'default':
            return '9'
        else:
            # This is almost but not quite a ISO 8613-3 code -- that
            # would use colons to separate the rgb values instead. But
            # it's what xterm, and hence everything else, supports.
            return '8;2;{};{};{}'.format(*self._urwid_name_to_rgb[color])

    def _attrspec_to_escape(self, a):
        return '\x1b[0;3{};4{}m'.format(
            self._cc(a.foreground),
            self._cc(a.background))


_is_linux_tty = None


def is_linux_tty():
    global _is_linux_tty
    if _is_linux_tty is None:
        try:
            r = fcntl.ioctl(sys.stdout.fileno(), KDGKBTYPE, ' ')
        except IOError as e:
            log.debug("KDGKBTYPE failed %r", e)
            return False
        log.debug("KDGKBTYPE returned %r, is_linux_tty %s", r, r == b'\x02')
        _is_linux_tty = r == b'\x02'
    return _is_linux_tty


def make_screen(ascii=False, inputf=None, outputf=None):
    """ """
    if inputf is None:
        inputf = sys.stdin
    if outputf is None:
        outputf = sys.stdout
    if is_linux_tty():
        return LinuxScreen(COLORS, input=inputf, output=outputf)
    elif ascii:
        return SubiquityScreen(input=inputf, output=outputf)
    else:
        return TwentyFourBitScreen(COLORS, input=inputf, output=outputf)
