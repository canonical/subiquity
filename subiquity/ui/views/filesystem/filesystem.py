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

""" Filesystem

Provides storage device selection and additional storage
configuration.

"""
import logging
from urwid import BoxAdapter, Text

from subiquitycore.ui.lists import SimpleList
from subiquitycore.ui.buttons import (done_btn,
                                      reset_btn,
                                      cancel_btn,
                                      menu_btn)
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView

from subiquity.models.filesystem import _humanize_size


log = logging.getLogger('subiquity.ui.filesystem.filesystem')


class FilesystemView(BaseView):
    def __init__(self, model, controller):
        log.debug('FileSystemView init start()')
        self.model = model
        self.controller = controller
        self.items = []
        self.model.probe_storage()  # probe before we complete
        self.body = [
            Padding.center_79(Text("FILE SYSTEM")),
            Padding.center_79(self._build_partition_list()),
            Padding.line_break(""),
            Padding.center_79(Text("AVAILABLE DISKS")),
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_79(self._build_menu()),
            Padding.line_break(""),
            Padding.center_79(self._build_used_disks()),
            Padding.fixed_10(self._build_buttons()),
        ]
        super().__init__(ListBox(self.body))
        log.debug('FileSystemView init complete()')

    def _build_used_disks(self):
        log.debug('FileSystemView: building used disks')
        pl = []
        for disk in self.model.get_used_disk_names():
            log.debug('used disk: {}'.format(disk))
            disk_string = disk
            disk_tag = self.model.get_tag(disk)
            if len(disk_tag):
                disk_string += " {}".format(disk_tag)
            pl.append(Color.info_minor(Text(disk_string)))
        if len(pl):
            return Pile(
                [Text("USED DISKS"),
                 Padding.line_break("")] + pl +
                [Padding.line_break("")]
            )

        return Pile(pl)

    def _build_partition_list(self):
        log.debug('FileSystemView: building part list')
        pl = []
        nr_parts = len(self.model.get_partitions())
        nr_fs = len(self.model.get_filesystems())
        if nr_parts == 0 and nr_fs == 0:
            pl.append(Color.info_minor(
                Text("No disks or partitions mounted")))
            log.debug('FileSystemView: no partitions')
            return Pile(pl)
        log.debug('FileSystemView: weve got partitions!')
        for dev in self.model.devices.values():
            for mnt, size, fstype, path in dev.get_fs_table():
                mnt = Text(mnt)
                size = Text("{}".format(_humanize_size(size)))
                fstype = Text(fstype) if fstype else '-'
                path = Text(path) if path else '-'
                partition_column = Columns([
                    (15, path),
                    size,
                    fstype,
                    mnt
                ], 4)
                pl.append(partition_column)
        log.debug('FileSystemView: build-part-list done')
        return Pile(pl)

    def _build_buttons(self):
        log.debug('FileSystemView: building buttons')
        buttons = []

        # don't enable done botton if we can't install
        if self.model.installable():
            buttons.append(
                Color.button(done_btn(on_press=self.done),
                             focus_map='button focus'))

        buttons.append(Color.button(reset_btn(on_press=self.reset),
                                    focus_map='button focus'))
        buttons.append(Color.button(cancel_btn(on_press=self.cancel),
                                    focus_map='button focus'))

        return Pile(buttons)

    def _get_percent_free(self, device):
        ''' return the device free space and percentage
            of the whole device'''
        percent = "%d" % (
            int((1.0 - (device.usedspace / device.size)) * 100))
        free = _humanize_size(device.freespace)
        rounded = "{}{}".format(int(float(free[:-1])), free[-1])
        return (rounded, percent)

    def _build_model_inputs(self):
        log.debug('FileSystemView: building model inputs')
        col_1 = []
        col_2 = []

        avail_disks = self.model.get_available_disk_names()
        if len(avail_disks) == 0:
            return Pile([Color.info_minor(Text("No available disks."))])

        for dname in avail_disks:
            disk = self.model.get_disk_info(dname)
            device = self.model.get_disk(dname)
            btn = menu_btn(label=disk.name,
                           on_press=self.show_disk_partition_view)

            col_1.append(
                Color.menu_button(btn, focus_map='menu_button focus'))
            disk_sz = _humanize_size(disk.size)
            log.debug('device partitions: {}'.format(len(device.partitions)))
            # if we've consumed some of the device, show
            # the remaining space and percentage of the whole
            if len(device.partitions) > 0:
                free, percent = self._get_percent_free(device)
                disk_sz = "{} ({}%) free".format(free, percent)
            col_2.append(Text(disk_sz))
            for partname in device.available_partitions:
                part = device.get_partition(partname)
                btn = menu_btn(label=partname,
                               on_press=self.show_disk_partition_view)
                col_1.append(
                    Color.menu_button(btn, focus_map='menu_button focus'))
                col_2.append(Text(_humanize_size(part.size)))

        col_1 = BoxAdapter(SimpleList(col_1),
                           height=len(col_1))
        col_2 = BoxAdapter(SimpleList(col_2, is_selectable=False),
                           height=len(col_2))
        return Columns([(16, col_1), col_2], 2)

    def _build_menu(self):
        log.debug('FileSystemView: building menu')
        opts = []
        avail_disks = self.model.get_available_disk_names()

        fs_menu = [
            # ('Connect iSCSI network disk',         'filesystem:connect-iscsi-disk'),
            # ('Connect Ceph network disk',          'filesystem:connect-ceph-disk'),
            # ('Create volume group (LVM2)',           'menu:filesystem:main:create-volume-group'),
            # ('Create software RAID (MD)',            'menu:filesystem:main:create-raid'),
            # ('Setup hierarchichal storage (bcache)', 'menu:filesystem:main:setup-bcache'),
        ]

        for opt, sig in fs_menu:
            if len(avail_disks) > 1:
                opts.append(Color.menu_button(
                            menu_btn(label=opt,
                                     on_press=self.on_fs_menu_press,
                                     user_data=sig),
                            focus_map='menu_button focus'))
        return Pile(opts)

    def on_fs_menu_press(self, result, sig):
        self.controller.signal.emit_signal(sig)

    def cancel(self, button):
        self.controller.cancel()

    def reset(self, button):
        self.controller.reset()

    def done(self, button):
        actions = self.model.get_actions()
        self.controller.finish(actions)

    def show_disk_partition_view(self, partition):
        self.controller.disk_partition(partition.label)
