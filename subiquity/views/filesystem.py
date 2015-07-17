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
import math
from urwid import (WidgetWrap, ListBox, Pile, BoxAdapter,
                   Text, Columns, LineBox, Edit, RadioButton)
from subiquity.ui.lists import SimpleList
from subiquity.ui.buttons import done_btn, reset_btn, cancel_btn
from subiquity.ui.utils import Padding, Color
from subiquity.signals import emit_signal


log = logging.getLogger('subiquity.filesystemView')


def _humanize_size(size):
    size = abs(size)
    if size == 0:
        return "0B"
    units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
    p = math.floor(math.log(size, 2) / 10)
    return "%.3f %s" % (size / math.pow(1024, p), units[int(p)])


class AddPartitionView(WidgetWrap):
    signals = [
        'fs:add-partition:done',
        'fs:add-partition:cancel'
    ]

    def __init__(self, model, selected_disk):
        self.partition_spec = {}
        self.model = model
        body = ListBox([
            Padding.center_79(
                Text("Adding partition to {}".format(selected_disk))),
            Padding.center_79(self._container()),
            Padding.center_79(self._build_buttons())
        ])
        box = BoxAdapter(body,
                         len(body))
        super().__init__(LineBox(box))

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button_secondary(cancel, focus_map='button_secondary focus'),
            Color.button_secondary(done, focus_map='button_secondary focus')
        ]
        return Pile(buttons)

    def _partition_edit(self):
        return Edit(caption="Partition number (1-4)",
                    edit_text="1")

    def _size_edit(self):
        return Edit(caption="Size (max 2Tb)")

    def _format_edit(self):
        group = []
        for fs in self.model.supported_filesystems:
            RadioButton(group, fs)
        return SimpleList(group)

    def _mount_point_edit(self):
        return Edit(caption="Mount", edit_text="/")

    def _container(self):
        total_items = [
            self._partition_edit(),
            self._size_edit(),
            self._format_edit(),
            self._mount_point_edit()
        ]

        return SimpleList(total_items)

    def cancel(self, button):
        emit_signal(self, 'fs:add-partition:done', False)

    def done(self):
        """ partition spec

        { 'partition_number': Int,
          'size': Int(M|G),
          'format' Str(ext4|btrfs..,
          'mount_point': Str
        }
        """
        if not self.partition_spec:
            # TODO: Maybe popup warning?
            return
        emit_signal(self, 'fs:add-partition:done', self.partition_spec)


class DiskPartitionView(WidgetWrap):
    signals = [
        'fs:dp:show-add-partition',
        'fs:dp:done',
    ]

    def __init__(self, model, selected_disk):
        self.model = model
        self.selected_disk = selected_disk
        self.body = [
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_79(self._build_menu()),
            Padding.line_break(""),
            Padding.center_20(self._build_buttons()),
        ]
        super().__init__(ListBox(self.body))

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button_secondary(cancel, focus_map='button_secondary focus'),
            Color.button_secondary(done, focus_map='button_secondary focus')
        ]
        return Pile(buttons)

    def _build_model_inputs(self):
        col_1 = []
        col_2 = []

        disk = self.model.get_disk_info(self.selected_disk)
        btn = done_btn(label="FREE SPACE", on_press=self.add_paritition)
        col_1.append(Color.button_primary(btn,
                                          focus_map='button_primary focus'))
        disk_sz = str(_humanize_size(disk.size))
        col_2.append(Text(disk_sz))

        col_1 = BoxAdapter(SimpleList(col_1),
                           height=len(col_1))
        col_2 = BoxAdapter(SimpleList(col_2, is_selectable=False),
                           height=len(col_2))
        return Columns([(15, col_1), col_2], 2)

    def _build_menu(self):
        opts = []
        for opt in self.model.partition_menu:
            opts.append(
                Color.button_secondary(done_btn(label=opt,
                                                on_press=self.done),
                                       focus_map='button_secondary focus'))
        return Pile(opts)

    def add_partition(self, partition):
        emit_signal(self, 'fs:dp:show-add-partition', True)

    def done(self, button):
        emit_signal(self, 'fs:dp:done', True)

    def cancel(self, button):
        emit_signal(self, 'fs:dp:done', False)


class FilesystemView(WidgetWrap):
    signals = [
        "fs:done",
        "fs:reset",
        "fs:dp:view"
    ]

    def __init__(self, model):
        self.model = model
        self.items = []
        self.body = [
            Padding.center_79(Text("FILE SYSTEM")),
            Padding.center_79(self._build_partition_list()),
            Padding.line_break(""),
            Padding.center_79(Text("AVAILABLE DISKS")),
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_79(self._build_menu()),
            Padding.line_break(""),
            self._build_used_disks(),
            Padding.center_20(self._build_buttons()),
        ]
        super().__init__(ListBox(self.body))

    def _build_used_disks(self):
        pl = []
        for disk in self.model.get_used_disks():
            pl.append(Text(disk.path))
        if len(pl):
            return Padding.center_79(Text("USED DISKS"),
                                     Padding.line_break(""),
                                     Pile(pl))
        return Pile(pl)

    def _build_partition_list(self):
        pl = []
        if len(self.model.get_partitions()) == 0:
            pl.append(Color.info_minor(
                Text("No disks or partitions mounted")))
            return Pile(pl)
        for part in self.model.get_partitions():
            pl.append(Text(part))
        return Pile(pl)

    def _build_buttons(self):
        buttons = [
            Color.button_secondary(reset_btn(on_press=self.reset),
                                   focus_map='button_secondary focus'),
            Color.button_secondary(done_btn(on_press=self.done),
                                   focus_map='button_secondary focus'),
        ]
        return Pile(buttons)

    def _build_model_inputs(self):
        col_1 = []
        col_2 = []

        for dname in self.model.get_available_disks():
            disk = self.model.get_disk_info(dname)
            btn = done_btn(label=disk.name,
                           on_press=self.show_disk_partition_view)

            col_1.append(
                Color.button_primary(btn, focus_map='button_primary focus'))
            disk_sz = str(_humanize_size(disk.size))
            col_2.append(Text(disk_sz))

        col_1 = BoxAdapter(SimpleList(col_1),
                           height=len(col_1))
        col_2 = BoxAdapter(SimpleList(col_2, is_selectable=False),
                           height=len(col_2))
        return Columns([(15, col_1), col_2], 2)

    def _build_menu(self):
        opts = []
        for opt in self.model.fs_menu:
            opts.append(
                Color.button_secondary(done_btn(label=opt,
                                                on_press=self.done),
                                       focus_map='button_secondary focus'))
        return Pile(opts)

    def done(self, button):
        log.info("Filesystem View done() getting disk info")
        actions = self.model.get_actions()
        emit_signal(self, 'fs:done', False, actions)

    def cancel(self, button):
        emit_signal(self, 'fs:done')

    def reset(self, button):
        emit_signal(self, 'fs:done', True)

    def show_disk_partition_view(self, partition):
        emit_signal(self, 'fs:dp:view', partition.label)
