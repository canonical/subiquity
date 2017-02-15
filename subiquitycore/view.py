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

""" View policy

Contains some default key navigations
"""

from urwid import Overlay, WidgetWrap


class BaseView(WidgetWrap):
    def show_overlay(self, overlay_widget, **kw):
        self.orig_w = self._w
        args = dict(
            align='center',
            width=('relative', 60),
            min_width=80,
            valign='middle',
            height='pack'
            )
        args.update(kw)
        self._w = Overlay(top_w=overlay_widget, bottom_w=self._w, **args)

    def remove_overlay(self):
        self._w = self.orig_w
        self.orig_w = None

    def keypress(self, size, key):
        if key in ['ctrl x']:
            self.controller.signal.emit_signal('control-x-quit')
            return None
        key = super().keypress(size, key)
        if key == 'esc':
            self.controller.cancel()
            return None
        return key
