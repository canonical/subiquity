# Portions Copyright 2017 Canonical, Ltd.
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

# This is adapted from
# https://github.com/pimutils/khal/commit/bd7c5f928a7670de9afae5657e66c6dc846688ac, which has this license:
#
# Copyright (c) 2013-2015 Christian Geier et al.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import logging

import urwid

log = logging.getLogger('subiquitycore.ui.frame')



def _maybe_select_first_selectable(w):
    """If w implements _select_first_selectable, call it."""
    m = getattr(w.base_widget, "_select_first_selectable", None)
    if m is not None:
        m()

def _maybe_select_last_selectable(w):
    """If w implements _select_last_selectable, call it."""
    m = getattr(w.base_widget, "_select_last_selectable", None)
    if m is not None:
        m()

class TabCyclingMixin:
    """Tab-cycling implementation that works with Pile and Columns."""

    def _select_first_selectable(self):
        """Select first selectable child (possibily recursively)."""
        log.debug("%s _select_first_selectable", self.__class__.__name__)
        i = self._first_selectable()
        self.set_focus(i)
        log.debug(" -> first selectable %s", self.contents[i][0])
        _maybe_select_first_selectable(self.contents[i][0])

    def _select_last_selectable(self):
        """Select last selectable child (possibily recursively)."""
        log.debug("%s _select_last_selectable", self.__class__.__name__)
        i = self._last_selectable()
        self.set_focus(i)
        log.debug(" -> last selectable %s", self.contents[i][0])
        self.set_focus(i)
        _maybe_select_last_selectable(self.contents[i][0])

    def _first_selectable(self):
        """return sequence number of self.contents last selectable item"""
        for j in range(0, len(self._contents)):
            if self._contents[j][0].selectable():
                return j
        return False

    def _last_selectable(self):
        """return sequence number of self._contents last selectable item"""
        for j in range(len(self._contents) - 1, - 1, - 1):
            if self._contents[j][0].selectable():
                return j
        return False

    def keypress(self, size, key):
        key = super(TabCyclingMixin, self).keypress(size, key)

        if key == 'tab':
            if self.focus_position == self._last_selectable():
                self._select_first_selectable()
                return key
            else:
                for i in range(self.focus_position + 1, len(self._contents)):
                    if self._contents[i][0].selectable():
                        self.set_focus(i)
                        _maybe_select_first_selectable(self._contents[i][0])
                        break
                else:  # no break
                    return key
        elif key == 'shift tab':
            if self.focus_position == self._first_selectable():
                self._select_last_selectable()
                return key
            else:
                for i in range(self.focus_position - 1, 0 - 1, -1):
                    if self._contents[i][0].selectable():
                        self.set_focus(i)
                        _maybe_select_last_selectable(self._contents[i][0])
                        break
                else:  # no break
                    return key
        else:
            return key


class TabCyclingPile(TabCyclingMixin, urwid.Pile):
    pass

class TabCyclingColumns(TabCyclingMixin, urwid.Columns):
    pass


class TabCyclingListBox(urwid.ListBox):
    def __init__(self, body):
        # urwid.ListBox converts a random sequence argument to a
        # PollingListWalker, which doesn't work with the below code.
        if getattr(body, 'get_focus', None) is None:
            body = urwid.SimpleListWalker(body)
        super().__init__(body)

    def _select_first_selectable(self):
        """Select first selectable child (possibily recursively)."""
        log.debug("%s _select_first_selectable", self.__class__.__name__)
        i = self._first_selectable()
        # We call set_focus twice because otherwise the listbox
        # attempts to do the minimal amount of scrolling required to
        # get the new focus widget into view, which is not what we
        # want, as if our first widget is a compound widget it results
        # its last widget being focused -- not at all what we want!
        self.set_focus(i)
        self.set_focus(i)
        # I don't really understand why this is required but it seems it is.
        self._invalidate()
        log.debug(" -> first selectable %s", self.body[i])
        _maybe_select_first_selectable(self.body[i])

    def _select_last_selectable(self):
        """Select last selectable child (possibily recursively)."""
        log.debug("%s _select_last_selectable", self.__class__.__name__)
        i = self._last_selectable()
        # See comment in _select_first_selectable for why we call this twice.
        self.set_focus(i)
        self.set_focus(i)
        self._invalidate()
        log.debug(" -> last selectable %s", self.body[i])
        _maybe_select_last_selectable(self.body[i])

    def _first_selectable(self):
        """return sequence number of self._contents last selectable item"""
        for j in range(0, len(self.body)):
            if self.body[j].selectable():
                return j
        return False

    def _last_selectable(self):
        """return sequence number of self.contents last selectable item"""
        for j in range(len(self.body) - 1, - 1, - 1):
            if self.body[j].selectable():
                return j
        return False

    def keypress(self, size, key):
        key = super().keypress(size, key)
        if key == 'tab':
            if self.focus_position == self._last_selectable():
                self._select_first_selectable()
                return key
            else:
                self._keypress_down(size)
        elif key == 'shift tab':
            if self.focus_position == self._first_selectable():
                self._select_last_selectable()
                return key
            else:
                self._keypress_up(size)
        else:
            return key

Columns = TabCyclingColumns
Pile = TabCyclingPile
ListBox = TabCyclingListBox
