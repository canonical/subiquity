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
import struct
import sys

log = logging.getLogger('subiquity.keycodes')

# /usr/include/linux/kd.h
K_RAW = 0x00
K_XLATE = 0x01
K_MEDIUMRAW = 0x02
K_UNICODE = 0x03
K_OFF = 0x04

KDGKBMODE = 0x4B44  # gets current keyboard mode
KDSKBMODE = 0x4B45  # sets current keyboard mode


class KeyCodesFilter:
    """input_filter that can pass (medium) raw keycodes to the application

    See http://lct.sourceforge.net/lct/x60.html for terminology.

    Call enter_keycodes_mode()/exit_keycodes_mode() to switch into and
    out of keycodes mode. In keycodes mode, the only events passed to
    the application are "press $N" / "release $N" where $N is the
    keycode the user pressed or released.

    Much of this is cribbed from the source of the "showkeys" utility.
    """

    def __init__(self):
        self._fd = os.open("/proc/self/fd/"+str(sys.stdin.fileno()), os.O_RDWR)
        self.filtering = False

    def enter_keycodes_mode(self):
        log.debug("enter_keycodes_mode")
        self.filtering = True
        # Read the old keyboard mode (it will proably always be K_UNICODE but
        # well).
        o = bytearray(4)
        fcntl.ioctl(self._fd, KDGKBMODE, o)
        self._old_mode = struct.unpack('i', o)[0]
        # Set the keyboard mode to K_MEDIUMRAW, which causes the keyboard
        # driver in the kernel to pass us keycodes.
        fcntl.ioctl(self._fd, KDSKBMODE, K_MEDIUMRAW)

    def exit_keycodes_mode(self):
        log.debug("exit_keycodes_mode")
        self.filtering = False
        fcntl.ioctl(self._fd, KDSKBMODE, self._old_mode)

    def filter(self, keys, codes):
        # Luckily urwid passes us the raw results from read() we can
        # turn into keycodes.
        if self.filtering:
            i = 0
            r = []
            n = len(codes)
            while i < len(codes):
                # This is straight from showkeys.c.
                if codes[i] & 0x80:
                    p = 'release '
                else:
                    p = 'press '
                if i + 2 < n and (codes[i] & 0x7f) == 0:
                    if (codes[i + 1] & 0x80) != 0:
                        if (codes[i + 2] & 0x80) != 0:
                            kc = (((codes[i + 1] & 0x7f) << 7) |
                                  (codes[i + 2] & 0x7f))
                            i += 3
                else:
                    kc = codes[i] & 0x7f
                    i += 1
                r.append(p + str(kc))
            return r
        else:
            return keys


class DummyKeycodesFilter:
    # A dummy implementation of the same interface as KeyCodesFilter
    # we can use when not running in a linux tty.

    def enter_keycodes_mode(self):
        pass

    def exit_keycodes_mode(self):
        pass

    def filter(self, keys, codes):
        return keys
