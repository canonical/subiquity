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
import logging
import types

import urwid

log = logging.getLogger('subiquity.signals')


class SignalException(Exception):
    "Problem with a signal"


class Signal:
    known_signals = []

    def register_signals(self, signals):
        if type(signals) is list:
            self.known_signals.extend(signals)
        else:
            self.known_signals.append(signals)
        urwid.register_signal(Signal, self.known_signals)

    def emit_signal(self, name, *args, **kwargs):
        urwid.emit_signal(self, name, *args, **kwargs)

    def connect_signal(self, name, cb):
        if isinstance(cb, types.MethodType):
            scb = "{}.{}".format(
                cb.__self__.__class__.__name__, cb.__func__.__name__)
        else:
            scb = str(cb)
        log.debug("connect_signal: %s -> %s", name, scb)
        urwid.connect_signal(self, name, cb)

    def connect_signals(self, signal_callback):
        """ Connects a batch of signals

        :param list signal_callback: List of tuples eg. ('signame', self.cb)
        """
        if not type(signal_callback) is list:
            raise SignalException(
                "Passed something other than a required list.")
        for sig, cb in signal_callback:
            if sig not in self.known_signals:
                self.register_signals(sig)
            self.connect_signal(sig, cb)
