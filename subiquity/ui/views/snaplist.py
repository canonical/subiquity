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

from urwid import (
    BOX,
    CheckBox,
    LineBox,
    RadioButton,
    Text,
    Widget,
    WidgetWrap,
    )

from subiquitycore.ui.buttons import ok_btn, cancel_btn, other_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.utils import button_pile, Color, Padding, screen
from subiquitycore.view import BaseView

from subiquity.models.filesystem import humanize_size
from subiquity.ui.spinner import Spinner

log = logging.getLogger("subiquity.views.snaplist")

class NoTabCyclingListBox(ListBox):
    def keypress(self, size, key):
        if not key.startswith("enter") and self._command_map[key] in ('next selectable', 'prev selectable'):
            return key
        else:
            return super().keypress(size, key)
    def _select_first_selectable(self):
        return
    def _select_last_selectable(self):
        return

class SnapInfoView(Widget):
    _selectable = True
    _sizing = frozenset([BOX])
    description_index = 5
    channels_index = 7
    def __init__(self, parent, snap, cur_risk):
        self.parent = parent
        self.snap = snap
        self.channels = []
        self.needs_focus = True
        channel_width = max(len(csi.channel_name) for csi in snap.channels) \
          + RadioButton.reserve_columns + 1
        max_version = max(len(csi.version) for csi in snap.channels)
        max_revision = max(len(str(csi.revision)) for csi in snap.channels) + 2
        max_size = max(len(humanize_size(csi.size)) for csi in snap.channels)
        radio_group = []
        for csi in snap.channels:
            notes = '-'
            if csi.confinement != "strict":
                notes = csi.confinement
            btn = RadioButton(
                radio_group,
                "{}:".format(csi.channel_name),
                state=csi.channel_name == cur_risk,
                on_state_change=self.state_change,
                user_data=csi.channel_name)
            self.channels.append(Columns([
                (channel_width, btn),
                (max_version, Text(csi.version)),
                (max_revision, Text("({})".format(csi.revision))),
                (max_size, Text(humanize_size(csi.size))),
                ('pack', Text(notes)),
                ], dividechars=1))
        self.description = Text(snap.description.replace('\r', '').strip())
        self.lb_description = Padding.center_79(ListBox([self.description]))
        self.lb_channels = Padding.center_79(NoTabCyclingListBox(self.channels))
        self.pile = Pile([
            ('pack', Text("")),
            ('pack', Padding.center_79(Text("{} - {}".format(snap.name, snap.publisher)))),
            ('pack', Text("")),
            ('pack', Padding.center_79(Text(snap.summary))),
            ('pack', Text("")),
            self.lb_description,
            ('pack', Text("")),
            ('weight', 1, self.lb_channels),
            ('pack', Text("")),
            ('pack', button_pile([other_btn(label=_("Close"), on_press=self.close)])),
            ('pack', Text("")),
            ])
    def close(self, sender=None):
        self.parent._w = self.parent.main_screen
    def state_change(self, sender, state, risk):
        if state:
            self.parent.snap_rows[self.snap.name].box.set_state(True)
            self.parent.to_install[self.snap.name] = risk
    def keypress(self, size, key):
        return self.pile.keypress(size, key)
    def render(self, size, focus):
        maxcol, maxrow = size
        rows_available = maxrow
        pack_option = self.pile.options('pack')
        for w, o in self.pile.contents:
            if o == pack_option:
                rows_available -= w.rows((maxcol,), focus)
        rows_wanted_description = Padding.center_79(self.description).rows((maxcol,), False)
        rows_wanted_channels = len(self.channels)
        if rows_wanted_channels + rows_wanted_description <= rows_available:
            description_rows = rows_wanted_description
        else:
            if rows_wanted_description < 2*rows_available/3:
                description_rows = rows_wanted_description
            else:
                channel_rows = min(rows_wanted_channels, int(rows_available/3))
                description_rows = rows_available - channel_rows
        self.pile.contents[self.description_index] = (self.lb_description, self.pile.options('given', description_rows))
        if description_rows >= rows_wanted_description:
            self.lb_description.original_widget._selectable = False
        else:
            self.lb_description.original_widget._selectable = True
        if self.needs_focus:
            self.pile._select_first_selectable()
            self.needs_focus = False
        return self.pile.render(size, focus)

class FetchingInfo(WidgetWrap):
    def __init__(self, parent, snap, loop):
        self.parent = parent
        self.spinner = Spinner(loop, style='dots')
        self.spinner.start()
        self.closed = False
        text = _("Fetching info for {}").format(snap.name)
        # | text |
        # 12    34
        self.width = len(text) + 4
        super().__init__(
            LineBox(
                Pile([
                    ('pack', Text(' ' + text)),
                    ('pack', self.spinner),
                    ('pack', button_pile([cancel_btn(label=_("Cancel"), on_press=self.close)])),
                    ])))
    def close(self, sender=None):
        if self.closed:
            return
        self.closed = True
        self.spinner.stop()
        self.parent.remove_overlay()

class SnapListRow(WidgetWrap):
    def __init__(self, parent, snap, max_name_len, max_publisher_len):
        self.parent = parent
        self.snap = snap
        self.box = CheckBox(snap.name, on_state_change=self.state_change)
        super().__init__(Color.menu_button(Columns([
                (max_name_len+4, self.box),
                Text(snap.summary, wrap='clip'),
                ], dividechars=1)))
    def keypress(self, size, key):
        if key.startswith("enter"):
            if self.snap.channels:
                self.parent._w = SnapInfoView(self.parent, self.snap, self.parent.to_install.get(self.snap.name))
                return
            else:
                fi = FetchingInfo(self.parent, self.snap, self.parent.controller.loop)
                self.parent.show_overlay(fi, width=fi.width)
                def cb():
                    if not fi.closed:
                        fi.close()
                        self.parent._w = SnapInfoView(self.parent, self.snap, self.parent.to_install.get(self.snap.name))
                self.parent.controller.info_for_snap(self.snap, cb)
                return
        return super().keypress(size, key)
    def state_change(self, sender, new_state):
        if new_state:
            self.parent.to_install[self.snap.name] = 'stable'
        else:
            self.parent.to_install.pop(self.snap.name, None)

class SnapListView(BaseView):

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.to_install = {} # {snap_name: risk}
        if self.controller.loader.state == "loading list":
            spinner = Spinner(controller.loop, style='dots')
            spinner.start()
            ok = ok_btn(label=_("Continue"), on_press=self.done)
            cancel = cancel_btn(label=_("Cancel"), on_press=self.done)
            p = button_pile([ok, cancel])
            def cb():
                spinner.stop()
                if self.controller.loader.state == "failed":
                    body = [Text(_("Loading server snaps from the store failed, sorry."))]
                    self._w = screen(body, button_pile([ok, cancel]))
                else:
                    self.make_main_screen()
                    self._w = self.main_screen
            self.controller.loader.ongoing[None].append(cb)
            body = [spinner]
            super().__init__(screen(
                body, button_pile([ok, cancel]),
                excerpt=_("Loading server snaps from store, please wait...")))
        else:
            self.make_main_screen()
            super().__init__(self.main_screen)

    def make_main_screen(self):
        snaps = self.model.get_snap_list()
        self.name_len = max([len(snap.name) for snap in snaps])
        self.publisher_len = max([len(snap.publisher) for snap in snaps])
        self.snap_rows = {}
        body = []
        for snap in snaps:
            row = SnapListRow(self, snap, self.name_len, self.publisher_len)
            self.snap_rows[snap.name] = row
            body.append(row)
        ok = ok_btn(label=_("OK"), on_press=self.done)
        cancel = cancel_btn(label=_("Cancel"), on_press=self.done)
        self.main_screen = screen(
            NoTabCyclingListBox(body), button_pile([ok, cancel]),
            focus_buttons=False,
            excerpt=_("These are popular snaps in server environments. Select or deselect with SPACE, press ENTER to see more details of the package, publisher and versions available."))

    def done(self, sender=None):
        log.debug("snaps to install %s", self.to_install)
        self.controller.done(self.to_install)

    def cancel(self, sender=None):
        if self._w is self.main_screen:
            self.controller.cancel()
        else:
            self._w = self.main_screen
