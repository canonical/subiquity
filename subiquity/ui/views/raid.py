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
from urwid import Text, CheckBox

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import cancel_btn, done_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.interactive import (StringEditor, IntegerEditor,
                                          Selector)
from subiquitycore.ui.utils import Color, Padding

from subiquity.models.filesystem import humanize_size

log = logging.getLogger('subiquity.ui.raid')


class RaidView(BaseView):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
        self.raid_level = Selector(self.model.raid_levels)
        self.hot_spares = IntegerEditor()
        self.chunk_size = StringEditor(edit_text="4K")
        self.selected_disks = []
        body = [
            Padding.center_50(self._build_disk_selection()),
            Padding.line_break(""),
            Padding.center_50(self._build_raid_configuration()),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        super().__init__(ListBox(body))

    def _build_disk_selection(self):
        log.debug('raid: _build_disk_selection')
        items = [
            Text("DISK SELECTION")
        ]

        # raid can use empty whole disks, or empty partitions
        avail_disks = self.model.get_empty_disk_names()
        avail_parts = self.model.get_empty_partition_names()
        avail_devs = sorted(avail_disks + avail_parts)
        if len(avail_devs) == 0:
            return items.append(
                [Color.info_minor(Text("No available disks."))])

        for dname in avail_devs:
            device = self.model.get_disk(dname)
            if device.path != dname:
                # we've got a partition
                raiddev = device.get_partition(dname)
            else:
                raiddev = device

            disk_sz = humanize_size(raiddev.size)
            disk_string = "{}     {},     {}".format(dname,
                                                     disk_sz,
                                                     device.model)
            log.debug('raid: disk_string={}'.format(disk_string))
            self.selected_disks.append(CheckBox(disk_string))

        items += self.selected_disks

        return Pile(items)

    def _build_raid_configuration(self):
        log.debug('raid: _build_raid_config')
        items = [
            Text("RAID CONFIGURATION"),
            Columns(
                [
                    ("weight", 0.2, Text("RAID Level", align="right")),
                    ("weight", 0.3, Color.string_input(self.raid_level))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Hot spares",
                                         align="right")),
                    ("weight", 0.3, Color.string_input(self.hot_spares))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Chunk size", align="right")),
                    ("weight", 0.3, Color.string_input(self.chunk_size))
                ],
                dividechars=4
            )
        ]
        return Pile(items)

    def _build_buttons(self):
        log.debug('raid: _build_buttons')
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done),
            Color.button(cancel)
        ]
        return Pile(buttons)

    def done(self, result):
        result = {
            'devices': [x.get_label() for x in self.selected_disks if x.state],
            'raid_level': self.raid_level.value,
            'hot_spares': self.hot_spares.value,
            'chunk_size': self.chunk_size.value,
        }
        log.debug('raid_done: result = {}'.format(result))
        self.signal.emit_signal('filesystem:add-raid-dev', result)

    def cancel(self, button):
        log.debug('raid: button_cancel')
        self.signal.prev_signal()
