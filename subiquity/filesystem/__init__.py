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
import json
import argparse

from subiquity.filesystem.blockdev import Blockdev
from probert import prober
from probert.storage import StorageInfo
import math
from urwid import (WidgetWrap, ListBox, Pile, BoxAdapter,
                   Text, Columns, LineBox, Edit, RadioButton)
from subiquity.ui.lists import SimpleList
from subiquity.ui.buttons import done_btn, reset_btn, cancel_btn
from subiquity.ui.utils import Padding, Color

log = logging.getLogger('subiquity.filesystem')


class FilesystemModel:
    """ Model representing storage options
    """

    fs_menu = [
        ('Connect iSCSI network disk',
         'filesystem:connect-iscsi-disk',
         'connect_iscsi_disk'),
        ('Connect Ceph network disk',
         'filesystem:connect-ceph-disk',
         'connect_ceph_disk'),
        ('Create volume group (LVM2)',
         'filesystem:create-volume-group',
         'create_volume_group'),
        ('Create software RAID (MD)',
         'filesystem:create-raid',
         'create_raid'),
        ('Setup hierarchichal storage (bcache)',
         'filesystem:setup-bcache',
         'setup_bcache')
    ]

    partition_menu = [
        ('Add first GPT partition',
         'filesystem:add-first-gpt-partition',
         'add_first_gpt_partition'),
        ('Format or create swap on entire device (unusual, advanced)',
         'filesystem:create-swap-entire-device',
         'create_swap_entire_device')
    ]

    supported_filesystems = [
        'ext4',
        'xfs',
        'btrfs',
        'swap',
        'bcache cache',
        'bcache store',
        'leave unformatted'
    ]

    def __init__(self):
        self.storage = {}
        self.info = {}
        self.devices = {}
        self.options = argparse.Namespace(probe_storage=True,
                                          probe_network=False)
        self.prober = prober.Prober(self.options)
        self.probe_storage()

    def get_signal_by_name(self, selection):
        for x, y, z in self.fs_menu:
            if x == selection:
                return y
        for x, y, z in self.partition_menu:
            if x == selection:
                return y

    def probe_storage(self):
        self.prober.probe()
        self.storage = self.prober.get_results().get('storage')
        log.debug('storage probe data:\n{}'.format(
                  json.dumps(self.storage, indent=4, sort_keys=True)))

        # TODO: replace this with Storage.get_device_by_match()
        # which takes a lambda fn for matching
        VALID_MAJORS = ['8', '253']
        for disk in self.storage.keys():
            if self.storage[disk]['DEVTYPE'] == 'disk' and \
               self.storage[disk]['MAJOR'] in VALID_MAJORS:
                log.debug('disk={}\n{}'.format(disk,
                          json.dumps(self.storage[disk], indent=4,
                                     sort_keys=True)))
                self.info[disk] = StorageInfo({disk: self.storage[disk]})

    def get_disk(self, disk):
        if disk not in self.devices:
                self.devices[disk] = Blockdev(disk, self.info[disk].serial)
        return self.devices[disk]

    def get_partitions(self):
        partitions = []
        for dev in self.devices.values():
            partnames = [part.path for part in dev.disk.partitions]
            partitions += partnames

        sorted(partitions)
        return partitions

    def get_available_disks(self):
        return sorted(self.info.keys())

    def get_used_disks(self):
        return [dev.disk.path for dev in self.devices.values()
                if dev.available is False]

    def get_disk_info(self, disk):
        return self.info[disk]

    def get_disk_action(self, disk):
        return self.devices[disk].get_actions()

    def get_actions(self):
        actions = []
        for dev in self.devices.values():
            actions += dev.get_actions()
        return actions


def _humanize_size(size):
    size = abs(size)
    if size == 0:
        return "0B"
    units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
    p = math.floor(math.log(size, 2) / 10)
    return "%.3f %s" % (size / math.pow(1024, p), units[int(p)])


class AddPartitionView(WidgetWrap):

    def __init__(self, model, signal, selected_disk):
        self.partition_spec = {}
        self.signal = signal
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
        self.signal.emit_signal('filesystem:finish-add-disk-partition')

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
        self.signal.emit_signal(
            'filesystem:finish-add-disk-partition', self.partition_spec)


class DiskPartitionView(WidgetWrap):
    def __init__(self, model, signal, selected_disk):
        self.model = model
        self.signal = signal
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
        self.signal.emit_signal('filesystem:add-disk-partition')

    def done(self, button):
        self.signal.emit_signal('filesystem:finish-disk-partition')

    def cancel(self, button):
        self.signal.emit_signal('filesystem:finish-disk-partition', False)


class FilesystemView(WidgetWrap):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
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
            #Color.button_secondary(done_btn(on_press=self.done),
             #                      focus_map='button_secondary focus'),
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
        for opt, sig, _ in self.model.fs_menu:
            opts.append(
                Color.button_secondary(
                    done_btn(label=opt,
                             on_press=self.on_fs_menu_press),
                    focus_map='button_secondary focus'))
        return Pile(opts)

    def on_fs_menu_press(self, result):
        log.info("Filesystem View done() getting disk info")
        actions = self.model.get_actions()
        self.signal.emit_signal(
            self.model.get_signal_by_name(result.label), False, actions)

    def cancel(self, button):
        self.signal.emit_signal('network:show')

    def reset(self, button):
        self.signal.emit_signal('filesystem:done', True)

    def show_disk_partition_view(self, partition):
        self.signal.emit_signal('filesystem:show-disk-partition',
                                partition.label)
