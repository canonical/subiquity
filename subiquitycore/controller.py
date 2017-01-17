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


from abc import ABC, abstractmethod
import logging
import os

log = logging.getLogger("subiquitycore.controller")

def view(func):
    n = func.__name__
    def f(self, *args, **kw):
        m = getattr(self, n)
        self.view_stack.append((m, args, kw))
        return func(self, *args, **kw)
    return f


class BaseController(ABC):
    """Base class for controllers."""

    signals = []

    def __init__(self, common):
        self.ui = common['ui']
        self.signal = common['signal']
        self.opts = common['opts']
        self.loop = common['loop']
        self.prober = common['prober']
        self.controllers = common['controllers']
        self.pool = common['pool']
        self.view_stack = []

    def register_signals(self):
        """Defines signals associated with controller from model."""
        signals = []
        for sig, cb in self.signals:
            signals.append((sig, getattr(self, cb)))
        self.signal.connect_signals(signals)

    def prev_view(self):
        self.view_stack.pop()
        meth, args, kw = self.view_stack.pop()
        meth(*args, **kw)

    def run_in_bg(self, func, callback):
        """Run func() in a thread and call callback on UI thread.

        callback will be passed a concurrent.futures.Future containing
        the result of func(). The result of callback is discarded. Any
        exception will be logged.
        """
        fut = self.pool.submit(func)
        def in_main_thread(ignored):
            try:
                callback(fut)
            except:
                log.exception("callback %s after calling %s failed", callback, func)
        pipe = self.loop.watch_pipe(in_main_thread)
        def in_random_thread(ignored):
            os.write(pipe, b'x')
        fut.add_done_callback(in_random_thread)

    @abstractmethod
    def cancel(self):
        pass

    @abstractmethod
    def default(self):
        pass
