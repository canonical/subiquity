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

import urwid

from subiquitycore.tests import SubiTestCase
from subiquitycore.view import BaseView
from subiquitycore.ui.stretchy import Stretchy, StretchyOverlay
from subiquitycore.ui.utils import undisabled


class TestStretchy(Stretchy):
    was_opened = was_closed = False

    def __init__(self):
        super().__init__("", [urwid.Text("")], 0, 0)

    def opened(self):
        self.was_opened = True

    def closed(self):
        self.was_closed = True


class TestBaseView(SubiTestCase):

    def get_stretchy_chain(self, view):
        view = view._w
        r = []
        while isinstance(view, StretchyOverlay):
            r.append(view.stretchy)
            view = undisabled(view.bottom_w)
        return r

    def test_basic(self):
        bv = BaseView(urwid.Text(""))
        s = TestStretchy()
        self.assertEqual(self.get_stretchy_chain(bv), [])
        bv.show_stretchy_overlay(s)
        self.assertTrue(s.was_opened)
        self.assertEqual(self.get_stretchy_chain(bv), [s])

        bv.remove_overlay()
        self.assertTrue(s.was_closed)
        self.assertEqual(self.get_stretchy_chain(bv), [])

        bv.show_stretchy_overlay(s)
        bv.remove_overlay(s)
        self.assertEqual(self.get_stretchy_chain(bv), [])

    def make_view_with_overlays(self):
        bv = BaseView(urwid.Text(""))
        a = TestStretchy()
        b = TestStretchy()
        c = TestStretchy()
        bv.show_stretchy_overlay(a)
        bv.show_stretchy_overlay(b)
        bv.show_stretchy_overlay(c)
        return bv, a, b, c

    def test_multiple(self):
        bv, a, b, c = self.make_view_with_overlays()
        self.assertEqual(self.get_stretchy_chain(bv), [c, b, a])

        bv, a, b, c = self.make_view_with_overlays()
        bv.remove_overlay(a)
        self.assertTrue(a.was_closed)
        self.assertEqual(self.get_stretchy_chain(bv), [c, b])

        bv, a, b, c = self.make_view_with_overlays()
        bv.remove_overlay(b)
        self.assertTrue(b.was_closed)
        self.assertEqual(self.get_stretchy_chain(bv), [c, a])

        bv, a, b, c = self.make_view_with_overlays()
        bv.remove_overlay(c)
        self.assertTrue(c.was_closed)
        self.assertEqual(self.get_stretchy_chain(bv), [b, a])

        bv, a, b, c = self.make_view_with_overlays()
        bv.remove_overlay()
        self.assertTrue(c.was_closed)
        self.assertEqual(self.get_stretchy_chain(bv), [b, a])
