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
from urwid import connect_signal, LineBox, Text, WidgetWrap

from subiquitycore.ui.buttons import (
    cancel_btn,
    continue_btn,
    done_btn,
    menu_btn,
    reset_btn,
    )
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView

from subiquity.models.filesystem import _humanize_size


log = logging.getLogger('subiquity.ui.filesystem.filesystem')


class FilesystemConfirmationView(WidgetWrap):
    def __init__(self, parent, controller):
        self.parent = parent
        self.controller = controller
        pile = Pile([
            Text("Selecting Continue below will result of the loss of data disks selected to be formatted. Are you sure you want to continue?"),
            Text(""),
            Padding.fixed_15(Color.button(cancel_btn(on_press=self.cancel))),
            Padding.fixed_15(Color.button(continue_btn(on_press=self.ok))),
            ])
        lb = LineBox(pile, title="Confirm destructive action")
        super().__init__(Padding.center_75(lb))

    def ok(self, sender):
        self.controller.finish()

    def cancel(self, sender):
        self.parent.remove_overlay()


class FilesystemView(BaseView):
    def __init__(self, model, controller):
        log.debug('FileSystemView init start()')
        self.model = model
        self.controller = controller
        self.items = []
        self.body = [
            Padding.center_79(Text("FILE SYSTEM")),
            Padding.line_break(""),
            Padding.center_79(self._build_filesystem_list()),
            Padding.line_break(""),
            Padding.center_79(Text("AVAILABLE DISKS AND PARTITIONS")),
            Padding.line_break(""),
            Padding.center_79(self._build_available_inputs()),
            Padding.line_break(""),
            #Padding.center_79(self._build_menu()),
            #Padding.line_break(""),
            #Padding.center_79(Text("USED DISKS")),
            #Padding.line_break(""),
            #Padding.center_79(self._build_used_disks()),
            #Padding.line_break(""),
            Padding.fixed_10(self._build_buttons()),
        ]
        super().__init__(ListBox(self.body))
        log.debug('FileSystemView init complete()')

    def _build_used_disks(self):
        log.debug('FileSystemView: building used disks')
        return Color.info_minor(Text("No disks have been used to create a constructed disk."))

    def _build_filesystem_list(self):
        log.debug('FileSystemView: building part list')
        cols = []
        for m in self.model._mounts:
            cols.append((m.device.volume.path, _humanize_size(m.device.volume.size), m.device.fstype, m.path))
        for fs in self.model._filesystems:
            if fs.fstype == 'swap':
                cols.append((fs.volume.path, _humanize_size(fs.volume.size), fs.fstype, 'SWAP'))

        if len(cols) == 0:
            return Pile([Color.info_minor(
                Text("No disks or partitions mounted."))])
        cols.insert(0, ("PARTITION", "SIZE", "TYPE", "MOUNT POINT"))
        pl = []
        for a, b, c, d in cols:
            pl.append(Columns([(15, Text(a)), Text(b), Text(c), Text(d)], 4))
        return Pile(pl)

    def _build_buttons(self):
        log.debug('FileSystemView: building buttons')
        buttons = []

        # don't enable done botton if we can't install
        if self.model.can_install():
            buttons.append(
                Color.button(done_btn(on_press=self.done)))

        buttons.append(Color.button(reset_btn(on_press=self.reset)))
        buttons.append(Color.button(cancel_btn(on_press=self.cancel)))

        return Pile(buttons)

    def _build_available_inputs(self):
        inputs = []

        def col(col1, col2, col3):
            inputs.append(Columns([(15, col1), (10, col2), col3], 2))

        col(Text("DEVICE"), Text("SIZE"), Text("TYPE"))

        for disk in self.model.all_disks():
            if disk.available:
                disk_btn = menu_btn(label=disk.path)
                connect_signal(disk_btn, 'click', self.click_disk, disk)
                col1 = Color.menu_button(disk_btn)
                col2 = Text(_humanize_size(disk.size))
                if disk.used > 0:
                    size = disk.size
                    free = disk.free
                    percent = int(100*free/size)
                    if percent == 0:
                        continue
                    col3 = Text("local disk, {} ({}%) free".format(_humanize_size(free), percent))
                else:
                    col3 = Text("local disk")
                col(col1, col2, col3)
            for partition in disk.partitions():
                if partition.available:
                    part_btn = menu_btn(label=' ' + partition.path)
                    connect_signal(part_btn, 'click', self.click_partition, partition)
                    col1 = Color.menu_button(part_btn)
                    if partition.fs() is not None:
                        fs = partition.fs().fstype
                    else:
                        fs = "unformatted"
                    col2 = Text(_humanize_size(partition.size))
                    col3 = Text("{} partition on local disk".format(fs))
                    col(col1, col2, col3)

        if len(inputs) == 1:
            return Pile([Color.info_minor(
                Text("No disks available."))])

        return Pile(inputs)

    def click_disk(self, sender, disk):
        self.controller.partition_disk(disk)

    def click_partition(self, sender, partition):
        self.controller.format_mount_partition(partition)

    def _build_menu(self):
        log.debug('FileSystemView: building menu')
        opts = []
        #avail_disks = self.model.get_available_disk_names()

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
                                     user_data=sig)))
        return Pile(opts)

    def cancel(self, button):
        self.controller.cancel()

    def reset(self, button):
        self.controller.reset()

    def done(self, button):
        self.show_overlay(FilesystemConfirmationView(self, self.controller))
