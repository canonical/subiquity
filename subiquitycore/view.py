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

import logging

from urwid import (
    emit_signal,
    Overlay,
    Text,
    )

from subiquitycore.ui.container import (
    Columns,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.stretchy import StretchyOverlay
from subiquitycore.ui.utils import disabled, undisabled


log = logging.getLogger('subiquitycore.view')


class BaseView(WidgetWrap):

    def local_help(self):
        """Help for what the user is currently looking at.

        Returns title, documentation (or None, None).
        """
        return None, None

    def show_overlay(self, overlay_widget, **kw):
        args = dict(
            align='center',
            width=('relative', 60),
            min_width=80,
            valign='middle',
            height='pack'
            )
        PADDING = 3
        # Don't expect callers to account for the padding if
        # they pass a fixed width.
        if 'width' in kw:
            if isinstance(kw['width'], int):
                kw['width'] += 2*PADDING
        args.update(kw)
        top = Pile([
            ('pack', Text("")),
            Columns([
                (PADDING, Text("")),
                overlay_widget,
                (PADDING, Text(""))
                ]),
            ('pack', Text("")),
            ])
        self._w = Overlay(top_w=top, bottom_w=disabled(self._w), **args)

    def show_stretchy_overlay(self, stretchy):
        emit_signal(stretchy, 'opened')
        stretchy.opened()
        self._w = StretchyOverlay(disabled(self._w), stretchy)

    def remove_overlay(self, stretchy=None):
        if stretchy is not None:
            one_above = None
            cur = self._w
            while isinstance(cur, (StretchyOverlay, Overlay)):
                cur_stretchy = getattr(cur, 'stretchy', None)
                if cur_stretchy is stretchy:
                    emit_signal(stretchy, 'closed')
                    stretchy.closed()
                    if one_above is not None:
                        one_above.bottom_w = cur.bottom_w
                    else:
                        self._w = undisabled(cur.bottom_w)
                    return
                one_above = cur
                cur = undisabled(cur.bottom_w)
        else:
            if isinstance(self._w, StretchyOverlay):
                emit_signal(self._w.stretchy, 'closed')
                self._w.stretchy.closed()
            self._w = undisabled(self._w.bottom_w)

    def cancel(self):
        pass

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == 'esc':
            if hasattr(self._w, 'bottom_w'):
                self.remove_overlay()
                return None
            else:
                self.cancel()
                return None
        return key
