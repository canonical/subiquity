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
    CheckBox,
    LineBox,
    ListBox as UrwidListBox,
    RadioButton,
    SelectableIcon,
    SimpleFocusListWalker,
    Text,
    )

from subiquitycore.ui.buttons import ok_btn, cancel_btn, other_btn
from subiquitycore.ui.container import (
    Columns,
    ListBox,
    Pile,
    ScrollBarListBox,
    WidgetWrap,
    )
from subiquitycore.ui.table import (
    AbstractTable,
    ColSpec,
    TableRow,
    )
from subiquitycore.ui.utils import button_pile, Color, screen
from subiquitycore.view import BaseView

from subiquity.models.filesystem import humanize_size
from subiquity.models.snaplist import SnapSelection
from subiquity.ui.spinner import Spinner

log = logging.getLogger("subiquity.views.snaplist")


class StarRadioButton(RadioButton):
    states = {
        True: SelectableIcon(" *"),
        False: SelectableIcon("  "),
        }
    reserve_columns = 3


class NoTabCyclingTableListBox(AbstractTable):

    def _make(self, rows):
        body = SimpleFocusListWalker(rows)
        return ScrollBarListBox(UrwidListBox(body))


class SnapInfoView(WidgetWrap):

    # This is mostly like a Pile but it tries to be a bit smart about
    # how to distribute space between the description and channel list
    # (which can both be arbitrarily long or short). If both are long,
    # the channel list is given a third of the space. If there is
    # space for both, they are packed into the upper part of the view.

    def __init__(self, parent, snap, cur_channel):
        self.parent = parent
        self.snap = snap
        self.channels = []
        self.needs_focus = True

        self.description = Text(snap.description.replace('\r', '').strip())
        self.lb_description = ListBox([self.description])

        radio_group = []
        for csi in snap.channels:
            notes = '-'
            if csi.confinement != "strict":
                notes = csi.confinement
            btn = StarRadioButton(
                radio_group,
                "{}:".format(csi.channel_name),
                state=csi.channel_name == cur_channel,
                on_state_change=self.state_change,
                user_data=SnapSelection(
                    channel=csi.channel_name,
                    is_classic=csi.confinement == "classic"))
            self.channels.append(Color.menu_button(TableRow([
                btn,
                Text(csi.version),
                Text("({})".format(csi.revision)),
                Text(humanize_size(csi.size)),
                Text(notes),
            ])))

        self.lb_channels = NoTabCyclingTableListBox(self.channels)

        title = Columns([
            Text(snap.name),
            ('pack', Text(
                _("Publisher: {}").format(snap.publisher),
                align='right')),
            ], dividechars=1)

        contents = [
            ('pack',      title),
            ('pack',      Text("")),
            ('pack',      Text(snap.summary)),
            ('pack',      Text("")),
            self.lb_description,  # overwritten in render()
            ('pack',      Text("")),
            ('weight', 1, self.lb_channels),
            ]
        self.description_index = contents.index(self.lb_description)
        self.pile = Pile(contents)
        super().__init__(self.pile)

    def state_change(self, sender, state, selection):
        if state:
            self.parent.snap_boxes[self.snap.name].set_state(True)
            self.parent.to_install[self.snap.name] = selection

    def render(self, size, focus):
        maxcol, maxrow = size

        rows_available = maxrow
        pack_option = self.pile.options('pack')
        for w, o in self.pile.contents:
            if o == pack_option:
                rows_available -= w.rows((maxcol,), focus)

        rows_wanted_description = self.description.rows((maxcol,), False)
        rows_wanted_channels = len(self.channels)

        if rows_wanted_channels + rows_wanted_description <= rows_available:
            description_rows = rows_wanted_description
        else:
            if rows_wanted_description < 2*rows_available/3:
                description_rows = rows_wanted_description
            else:
                channel_rows = min(rows_wanted_channels, int(rows_available/3))
                description_rows = rows_available - channel_rows

        self.pile.contents[self.description_index] = (
            self.lb_description, self.pile.options('given', description_rows))
        if description_rows >= rows_wanted_description:
            self.lb_description.base_widget._selectable = False
        else:
            self.lb_description.base_widget._selectable = True
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
        cancel = cancel_btn(label=_("Cancel"), on_press=self.close)
        super().__init__(
            LineBox(
                Pile([
                    ('pack', Text(' ' + text)),
                    ('pack', self.spinner),
                    ('pack', button_pile([cancel])),
                    ])))

    def close(self, sender=None):
        if self.closed:
            return
        self.closed = True
        self.spinner.stop()
        self.parent.remove_overlay()


class FetchingFailed(WidgetWrap):

    def __init__(self, row, snap):
        self.row = row
        self.closed = False
        text = _("Fetching info for {} failed").format(snap.name)
        # | text |
        # 12    34
        self.width = len(text) + 4
        retry = other_btn(label=_("Try again"), on_press=self.load)
        cancel = cancel_btn(label=_("Cancel"), on_press=self.close)
        super().__init__(
            LineBox(
                Pile([
                    ('pack', Text(' ' + text)),
                    ('pack', button_pile([retry, cancel])),
                    ])))

    def load(self, sender=None):
        self.close()
        self.row.load_info()

    def close(self, sender=None):
        if self.closed:
            return
        self.closed = True
        self.row.parent.remove_overlay()


class SnapCheckBox(CheckBox):
    states = {
        True: SelectableIcon(" *"),
        False: SelectableIcon("  "),
        }
    reserve_columns = 3

    def __init__(self, parent, snap):
        self.parent = parent
        self.snap = snap
        super().__init__(snap.name, on_state_change=self.state_change)

    def load_info(self):
        called = False
        fi = None

        def callback():
            nonlocal called
            called = True
            if fi is not None:
                fi.close()
            if len(self.snap.channels) == 0:  # or other indication of failure
                ff = FetchingFailed(self, self.snap)
                self.parent.show_overlay(ff, width=ff.width)
            else:
                cur_chan = None
                if self.snap.name in self.parent.to_install:
                    cur_chan = self.parent.to_install[self.snap.name].channel
                self.parent.show_screen(screen(
                    SnapInfoView(self.parent, self.snap, cur_chan),
                    [other_btn(
                        label=_("Close"),
                        on_press=self.parent.show_main_screen)],
                    focus_buttons=False))
        self.parent.controller.get_snap_info(self.snap, callback)
        # If we didn't get callback synchronously, display a dialog
        # while the info loads.
        if not called:
            fi = FetchingInfo(
                self.parent, self.snap, self.parent.controller.loop)
            self.parent.show_overlay(fi, width=fi.width)

    def keypress(self, size, key):
        if key.startswith("enter"):
            self.load_info()
        else:
            return super().keypress(size, key)

    def state_change(self, sender, new_state):
        if new_state:
            self.parent.to_install[self.snap.name] = SnapSelection(
                channel='stable',
                is_classic=self.snap.confinement == "classic")
        else:
            self.parent.to_install.pop(self.snap.name, None)


class SnapListView(BaseView):

    title = _("Featured Server Snaps")

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        self.to_install = {}  # {snap_name: (channel, is_classic)}
        self.load()

    def load(self, sender=None):
        spinner = None
        called = False

        def callback(snap_list):
            nonlocal called
            called = True
            if spinner is not None:
                spinner.stop()
            if len(snap_list) == 0:
                self.offer_retry()
            else:
                self.make_main_screen(snap_list)
                self.show_main_screen()
        self.controller.get_snap_list(callback)
        if called:
            return
        spinner = Spinner(self.controller.loop, style='dots')
        spinner.start()
        self._w = screen(
            [spinner], [ok_btn(label=_("Continue"), on_press=self.done)],
            excerpt=_("Loading server snaps from store, please wait..."))

    def offer_retry(self):
        self._w = screen(
            [Text(_("Sorry, loading snaps from the store failed."))],
            [
                other_btn(label=_("Try again"), on_press=self.load),
                ok_btn(label=_("Continue"), on_press=self.done),
            ])

    def show_main_screen(self, sender=None):
        self._w = self._main_screen

    def show_screen(self, screen):
        self._w = screen

    def make_main_screen(self, snap_list):
        self.snap_boxes = {}
        body = []
        for snap in snap_list:
            box = self.snap_boxes[snap.name] = SnapCheckBox(self, snap)
            row = [
                box,
                Text(snap.publisher),
                Text(snap.summary, wrap='clip'),
                ]
            body.append(Color.menu_button(TableRow(row)))
        table = NoTabCyclingTableListBox(
            body,
            colspecs={
                1: ColSpec(omittable=True),
                2: ColSpec(pack=False, min_width=40),
                })
        ok = ok_btn(label=_("Done"), on_press=self.done)
        cancel = cancel_btn(label=_("Back"), on_press=self.cancel)
        self._main_screen = screen(
            table, [ok, cancel],
            focus_buttons=False,
            excerpt=_(
                "These are popular snaps in server environments. Select or "
                "deselect with SPACE, press ENTER to see more details of the "
                "package, publisher and versions available."))

    def done(self, sender=None):
        log.debug("snaps to install %s", self.to_install)
        self.controller.done(self.to_install)

    def cancel(self, sender=None):
        if self._w is self._main_screen:
            self.controller.cancel()
        else:
            self.show_main_screen()
