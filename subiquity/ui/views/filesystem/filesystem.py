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
from urwid import (
    connect_signal,
    LineBox,
    Padding as UrwidPadding,
    Text,
    WidgetWrap,
    )

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

from subiquity.models.filesystem import humanize_size


log = logging.getLogger('subiquity.ui.filesystem.filesystem')


confirmation_text = """
Selecting Continue below will result of the loss of data on the disks selected to be formatted.

Are you sure you want to continue?
"""

class FilesystemConfirmationView(WidgetWrap):
    def __init__(self, parent, controller):
        self.parent = parent
        self.controller = controller
        pile = Pile([
            UrwidPadding(Text(confirmation_text), left=2, right=2),
            Padding.fixed_15(Color.button(cancel_btn(label="No", on_press=self.cancel))),
            Padding.fixed_15(Color.button(continue_btn(on_press=self.ok))),
            Text(""),
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
            Text("FILE SYSTEM SUMMARY"),
            Text(""),
            Padding.push_4(self._build_filesystem_list()),
            Text(""),
            Text("AVAILABLE DEVICES"),
            Text(""),
            Padding.push_4(self._build_available_inputs()),
            Text(""),
            #self._build_menu(),
            #Text(""),
            #Text("USED DISKS"),
            #Text(""),
            #self._build_used_disks(),
            #Text(""),
            Padding.fixed_10(self._build_buttons()),
        ]
        super().__init__(Padding.center_95(ListBox(self.body)))
        log.debug('FileSystemView init complete()')

    def _build_used_disks(self):
        log.debug('FileSystemView: building used disks')
        return Color.info_minor(Text("No disks have been used to create a constructed disk."))

    def _build_filesystem_list(self):
        log.debug('FileSystemView: building part list')
        cols = []
        longest_path = len("MOUNT POINT")
        for m in sorted(self.model._mounts, key=lambda m:m.path):
            path = m.path
            longest_path = max(longest_path, len(path))
            for p, *_ in reversed(cols):
                if path.startswith(p):
                    path = [('info_minor', p), path[len(p):]]
                    break
            cols.append((m.path, path, humanize_size(m.device.volume.size), m.device.fstype, m.device.volume.desc()))
        for fs in self.model._filesystems:
            if fs.fstype == 'swap':
                cols.append((None, 'SWAP', humanize_size(fs.volume.size), fs.fstype, fs.volume.desc()))

        if len(cols) == 0:
            return Pile([Color.info_minor(
                Text("No disks or partitions mounted."))])
        cols.insert(0, (None, "MOUNT POINT", "SIZE", "TYPE", "DEVICE TYPE"))
        pl = []
        for _, a, b, c, d in cols:
            if b == "SIZE":
                b = Text(b, align='center')
            else:
                b = Text(b, align='right')
            pl.append(Columns([(longest_path, Text(a)), (9, b), (self.model.longest_fs_name, Text(c)), Text(d)], 4))
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

        def col3(col1, col2, col3):
            inputs.append(Columns([(40, col1), (10, col2), (10, col3)], 2))
        def col2(col1, col2):
            inputs.append(Columns([(40, col1), col2], 2))
        def col1(col1):
            inputs.append(Columns([(40, col1)], 1))

        col3(Text("DEVICE"), Text("SIZE", align="center"), Text("TYPE"))

        for disk in self.model.all_disks():
            disk_label = Text(disk.serial)
            size = Text(humanize_size(disk.size).rjust(9))
            typ = Text(disk.desc())
            col3(disk_label, size, typ)
            fs = disk.fs()
            if fs is not None:
                label = "entire device, "
                fs_obj = self.model.fs_by_name[fs.fstype]
                if fs.mount():
                    label += "%-*s"%(self.model.longest_fs_name+2, fs.fstype+',') + fs.mount().path
                else:
                    label += fs.fstype
                if fs_obj.label and fs_obj.is_mounted and not fs.mount():
                    disk_btn = menu_btn(label=label)
                    connect_signal(disk_btn, 'click', self.click_disk, disk)
                    disk_btn = Color.menu_button(disk_btn)
                else:
                    disk_btn = Color.info_minor(Text("  " + label))
                col1(disk_btn)
            for partition in disk.partitions():
                label = "partition {}, ".format(partition.number)
                fs = partition.fs()
                if fs is not None:
                    if fs.mount():
                        label += "%-*s"%(self.model.longest_fs_name+2, fs.fstype+',') + fs.mount().path
                    else:
                        label += fs.fstype
                else:
                    label += "unformatted"
                size = Text("{:>9} ({}%)".format(humanize_size(partition.size), int(100*partition.size/disk.size)))
                if partition.available:
                    part_btn = menu_btn(label=label)
                    connect_signal(part_btn, 'click', self.click_partition, partition)
                    part_btn = Color.menu_button(part_btn)
                    col2(part_btn, size)
                else:
                    part_btn = Color.info_minor(Text("  " + label))
                    size = Color.info_minor(size)
                    col2(part_btn, size)
            size = disk.size
            free = disk.free
            percent = int(100*free/size)
            if disk.available and disk.used > 0 and percent > 0:
                disk_btn = menu_btn(label="ADD/EDIT PARTITIONS")
                connect_signal(disk_btn, 'click', self.click_disk, disk)
                disk_btn = Color.menu_button(disk_btn)
                size = Text("{:>9} ({}%) free".format(humanize_size(free), percent))
                col2(disk_btn, size)
            elif disk.available and percent > 0:
                disk_btn = menu_btn(label="ADD FIRST PARTITION")
                connect_signal(disk_btn, 'click', self.click_disk, disk)
                disk_btn = Color.menu_button(disk_btn)
                col2(disk_btn, Text(""))
            else:
                disk_btn = menu_btn(label="EDIT PARTITIONS")
                connect_signal(disk_btn, 'click', self.click_disk, disk)
                disk_btn = Color.menu_button(disk_btn)
                col2(disk_btn, Text(""))

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

    def cancel(self, button=None):
        self.controller.cancel()

    def reset(self, button):
        self.controller.reset()

    def done(self, button):
        self.show_overlay(FilesystemConfirmationView(self, self.controller))
