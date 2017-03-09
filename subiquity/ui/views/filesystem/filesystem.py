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
from urwid import BoxAdapter, connect_signal, Text

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
        self.model.probe()  # probe before we complete
        self.body = [
            Padding.center_79(Text("FILE SYSTEM")),
            Padding.center_79(self._build_filesystem_list()),
            Padding.line_break(""),
            Padding.center_79(Text("AVAILABLE DISKS")),
            Padding.center_79(self._build_available_inputs()),
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
        return Text("")
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

    def _build_filesystem_list(self):
        log.debug('FileSystemView: building part list')
        mounts = sorted(self.model._mounts, key=lambda m:m.device.volume.path)
        if len(mounts) == 0:
            return Pile([Color.info_minor(
                Text("No disks or partitions mounted"))])
        pl = []
        for m in mounts:
            col = Columns([
                    (15, m.device.volume.path),
                    _humanize_size(m.device.volume.size),
                    m.device.fstype,
                    m.path,
                ], 4)
            pl.append(col)
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

    def _get_percent_free(self, device):
        ''' return the device free space and percentage
            of the whole device'''
        percent = "%d" % (
            int((1.0 - (device.usedspace / device.size)) * 100))
        free = _humanize_size(device.freespace)
        rounded = "{}{}".format(int(float(free[:-1])), free[-1])
        return (rounded, percent)

    def _build_available_inputs(self):
        inputs = []

        for disk in self.model.all_disks():
            if not disk.available:
                continue
            available_partitions = []
            for partition in disk._partitions:
                if partition.available:
                    available_partitions.append(partition)
            if len(available_partitions):
                pass
            elif disk.used > 0:
                col1 = menu_btn(label=disk.path)
                connect_signal(col1, 'click', self.click_disk, disk)
                size = disk.size
                free = disk.size - disk.used
                percent = int(100*free/size)
                if percent == 0:
                    continue
                col2 = "{} ({}%)".format(_humanize_size(free), percent)
                inputs.append(Columns([col1, col2]))
            else:
                inputs.append(menu_btn(label=disk.path))
        return Pile(inputs)

    def click_disk(self, sender, disk):
        self.controller.partition_disk(disk)

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
