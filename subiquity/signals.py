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

import urwid

SIGNALS = {}


def register_signal(obj, name):
    if obj.__class__ not in SIGNALS:
        SIGNALS[obj.__class__] = []
    if name not in SIGNALS[obj.__class__]:
        SIGNALS[obj.__class__].append(name)
        urwid.register_signal(obj.__class__, SIGNALS[obj.__class__])


def emit_signal(obj, name, args):
    register_signal(obj, name)
    urwid.emit_signal(obj, name, args)
