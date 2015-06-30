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
from urwid.main_loop import ExitMainLoop

log = logging.getLogger('subiquity.loop_shim')


class AsyncioEventLoop(object):
    """
    Event loop based on the standard library ``asyncio`` module.
    ``asyncio`` is new in Python 3.4, but also exists as a backport on PyPI for
    Python 3.3.  The ``trollius`` package is available for older Pythons with
    slightly different syntax, but also works with this loop.
    """
    _we_started_event_loop = False

    _idle_emulation_delay = 1.0 / 256  # a short time (in seconds)

    def __init__(self, **kwargs):
        log.debug("Running the AsyncioEventLoop shim because current "
                  "version of urwid < 1.3.0")
        if 'loop' in kwargs:
            self._loop = kwargs.pop('loop')
        else:
            import asyncio
            self._loop = asyncio.get_event_loop()

    def alarm(self, seconds, callback):
        """
        Call callback() a given time from now.  No parameters are
        passed to callback.
        Returns a handle that may be passed to remove_alarm()
        seconds -- time in seconds to wait before calling callback
        callback -- function to call from event loop
        """
        return self._loop.call_later(seconds, callback)

    def remove_alarm(self, handle):
        """
        Remove an alarm.
        Returns True if the alarm exists, False otherwise
        """
        existed = not handle._cancelled
        handle.cancel()
        return existed

    def watch_file(self, fd, callback):
        """
        Call callback() when fd has some data to read.  No parameters
        are passed to callback.
        Returns a handle that may be passed to remove_watch_file()
        fd -- file descriptor to watch for input
        callback -- function to call when input is available
        """
        self._loop.add_reader(fd, callback)
        return fd

    def remove_watch_file(self, handle):
        """
        Remove an input file.
        Returns True if the input file exists, False otherwise
        """
        return self._loop.remove_reader(handle)

    def enter_idle(self, callback):
        """
        Add a callback for entering idle.
        Returns a handle that may be passed to remove_idle()
        """
        # XXX there's no such thing as "idle" in most event loops; this fakes
        # it the same way as Twisted, by scheduling the callback to be called
        # repeatedly
        mutable_handle = [None]

        def faux_idle_callback():
            callback()
            mutable_handle[0] = self._loop.call_later(
                self._idle_emulation_delay, faux_idle_callback)

        mutable_handle[0] = self._loop.call_later(
            self._idle_emulation_delay, faux_idle_callback)

        return mutable_handle

    def remove_enter_idle(self, handle):
        """
        Remove an idle callback.
        Returns True if the handle was removed.
        """
        # `handle` is just a list containing the current actual handle
        return self.remove_alarm(handle[0])

    _exc_info = None

    def _exception_handler(self, loop, context):
        exc = context.get('exception')
        if exc:
            loop.stop()
            if not isinstance(exc, ExitMainLoop):
                # Store the exc_info so we can re-raise after the loop stops
                import sys
                self._exc_info = sys.exc_info()
        else:
            loop.default_exception_handler(context)

    def run(self):
        """
        Start the event loop.  Exit the loop when any callback raises
        an exception.  If ExitMainLoop is raised, exit cleanly.
        """
        self._loop.set_exception_handler(self._exception_handler)
        self._loop.run_forever()
        if self._exc_info:
            raise Exception(self._exc_info[0],
                            self._exc_info[1],
                            self._exc_info[2])
            self._exc_info = None
