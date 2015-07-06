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
from urwid import (WidgetWrap, ListBox, Pile, BoxAdapter, Text, Columns)
from subiquity.ui.lists import SimpleList
from subiquity.ui.buttons import confirm_btn, cancel_btn
from subiquity.ui.utils import Padding, Color


log = logging.getLogger('subiquity.filesystemView')


def _humanize_size(size):
    size = abs(size)
    if size == 0:
        return "0B"
    units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
    p = math.floor(math.log(size, 2) / 10)
    return "%.3f %s" % (size / math.pow(1024, p), units[int(p)])


class FilesystemView(WidgetWrap):
    def __init__(self, model, cb):
        self.model = model
        self.cb = cb
        self.items = []
        self.body = [
            Padding.center_79(Text("FILE SYSTEM")),
            Padding.center_79(self._build_partition_list()),
            Padding.line_break(""),
            Padding.center_79(Text("AVAILABLE DISKS")),
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_79(self._build_additional_options()),
            Padding.line_break(""),
            Padding.center_20(self._build_buttons()),
        ]
        super().__init__(ListBox(self.body))

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
            Color.button_secondary(cancel_btn(on_press=self.cancel),
                                   focus_map='button_secondary focus'),
        ]
        return Pile(buttons)

    def _build_model_inputs(self):
        col_1 = []
        col_2 = []

        for dname in self.model.get_available_disks():
            disk = self.model.get_disk_info(dname)
            col_1.append(
                Color.button_primary(confirm_btn(label=disk.name,
                                                 on_press=self.confirm),
                                     focus_map='button_primary focus'))
            disk_sz = str(_humanize_size(disk.size))
            col_2.append(Text(disk_sz))

        col_1 = BoxAdapter(SimpleList(col_1),
                           height=len(col_1))
        col_2 = BoxAdapter(SimpleList(col_2, is_selectable=False),
                           height=len(col_2))
        return Columns([(15, col_1), col_2], 2)

    def _build_additional_options(self):
        opts = []
        for opt in self.model.additional_options:
            opts.append(
                Color.button_secondary(confirm_btn(label=opt,
                                                   on_press=self.confirm),
                                       focus_map='button_secondary focus'))
        return Pile(opts)

    def confirm(self, button):
        log.info("Filesystem View confirm() getting disk info")
        disk = self.model.get_disk_info(button.label)
        log.info("Filesystem View callback({}, {}, {})".format(disk.name,
                                                               disk.model,
                                                               disk.serial))
        return self.cb(disk.name, disk.model, disk.serial)

    def cancel(self, button):
        return self.cb(None)
