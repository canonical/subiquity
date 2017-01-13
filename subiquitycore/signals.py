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


""" Registers all known signal emitters
"""
import urwid
import logging

log = logging.getLogger('subiquity.signals')


class SignalException(Exception):
    "Problem with a signal"


class Signal:
    known_signals = []
    signal_stack = []

    def register_signals(self, signals):
        if type(signals) is list:
            self.known_signals.extend(signals)
        else:
            self.known_signals.append(signals)
        urwid.register_signal(Signal, signals)

    def prev_signal(self):
        log.debug('prev_signal: before: '
                  'size={} stack={}'.format(len(self.signal_stack),
                                            self.signal_stack))
        if len(self.signal_stack) > 1:
            (current_name, *_) = self.signal_stack.pop()
            (prev_name, args, kwargs) = self.signal_stack.pop()
            log.debug('current_name={}'.format(current_name))
            log.debug('previous={}'.format(prev_name))
            while (current_name.count(':') < prev_name.count(':') or
                   current_name == prev_name):
                log.debug('get next previous')
                (prev_name, args, kwargs) = self.signal_stack.pop()
                log.debug('previous={}'.format(prev_name))

            log.debug('prev_signal: after: '
                      'size={} stack={}'.format(len(self.signal_stack),
                                                self.signal_stack))

            log.debug("PrevEmitter: {}, {}, {}".format(prev_name, args,
                                                       kwargs))
            self.emit_signal(prev_name, *args, **kwargs)
        else:
            log.debug('stack empty: emitting menu:welcome:main')
            # FIXME: this should be set by common
            urwid.emit_signal(self, 'menu:welcome:main')

    def emit_signal(self, name, *args, **kwargs):
        # Disabled because it can reveal credentials in the arguments.
        #log.debug("Emitter: {}, {}, {}".format(name, args, kwargs))
        if name.startswith("menu:"):
            log.debug(" emit: before: "
                      "size={} stack={}".format(len(self.signal_stack),
                                                self.signal_stack))
            # only stack *menu* signals, drop signals if we've already
            # visited this level
            match = [s for s in self.signal_stack if s[0] == name]
            if len(match) > 0:
                index = self.signal_stack.index(match.pop())
                log.debug('Already visited {}, trimming stack'.format(name))
                self.signal_stack = self.signal_stack[0:index + 1]
            else:
                log.debug('New menu for stack: {}'.format(name))
                self.signal_stack.append((name, args, kwargs))

            log.debug(" emit: after: "
                      "size={} stack={}".format(len(self.signal_stack),
                                                self.signal_stack))
        urwid.emit_signal(self, name, *args, **kwargs)

    def connect_signal(self, name, cb, **kwargs):
        log.debug(
            "Emitter Connection: {}, {}, {}".format(name,
                                                    cb,
                                                    kwargs))
        urwid.connect_signal(self, name, cb, **kwargs)

    def connect_signals(self, signal_callback):
        """ Connects a batch of signals

        :param list signal_callback: List of tuples
                                     eg. ('menu:welcome:show', self.cb)
        """
        if not type(signal_callback) is list:
            raise SignalException(
                "Passed something other than a required list.")
        for sig, cb in signal_callback:
            if sig not in self.known_signals:
                self.register_signals(sig)
            self.connect_signal(sig, cb)

    def __repr__(self):
        return "Known Signals: {}".format(self.known_signals)
