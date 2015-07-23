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
                   Text, Columns)
from subiquity.ui.lists import SimpleList
from subiquity.ui.buttons import done_btn, reset_btn, cancel_btn
from subiquity.ui.widgets import Box
from subiquity.ui.utils import Padding, Color
from subiquity.ui.interactive import (StringEditor, IntegerEditor, Selector)
from subiquity.model import ModelPolicy
from subiquity.view import ViewPolicy

log = logging.getLogger('subiquity.filesystem')


class FilesystemModel(ModelPolicy):
    """ Model representing storage options
    """
    prev_signal = (
        'Back to network path',
        'network:show',
        'network'
    )

    signals = [
        ('Filesystem view',
         'filesystem:show',
         'filesystem'),
        ('Filesystem finish',
         'filesystem:finish',
         'filesystem_handler'),
        ('Show disk partition view',
         'filesystem:show-disk-partition',
         'disk_partition'),
        ('Finish disk partition',
         'filesystem:finish-disk-partition',
         'disk_partition_handler'),
        ('Add disk partition',
         'filesystem:add-disk-partition',
         'add_disk_partition'),
        ('Finish add disk partition',
         'filesystem:finish-add-disk-partition',
         'add_disk_partition_handler'),
        ('Format or create swap on entire device (unusual, advanced)',
         'filesystem:create-swap-entire-device',
         'create_swap_entire_device')
    ]

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
        for x, y, z in self.get_signals():
            if x == selection:
                return y

    def get_signals(self):
        return self.signals + self.fs_menu

    def get_menu(self):
        return self.fs_menu

    def probe_storage(self):
        self.prober.probe()
        self.storage = self.prober.get_results().get('storage')
        # TODO: Put this into a logging namespace for probert
        #       since its quite a bit of log information.
        # log.debug('storage probe data:\n{}'.format(
        #          json.dumps(self.storage, indent=4, sort_keys=True)))

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


def _dehumanize_size(size):
    # convert human 'size' to integer
    size_in = size
    if size.endswith("B"):
        size = size[:-1]

    mpliers = {'B': 1, 'K': 2 ** 10, 'M': 2 ** 20, 'G': 2 ** 30, 'T': 2 ** 40}

    num = size
    mplier = 'B'
    for m in mpliers:
        if size.endswith(m):
            mplier = m
            num = size[0:-len(m)]

    try:
        num = float(num)
    except ValueError:
        raise ValueError("'{}' is not valid input.".format(size_in))

    if num < 0:
        raise ValueError("'{}': cannot be negative".format(size_in))

    return int(num * mpliers[mplier])


class AddPartitionView(WidgetWrap):

    def __init__(self, model, signal, selected_disk):
        self.model = model
        self.signal = signal
        self.selected_disk = self.model.get_disk(selected_disk)

        self.partnum = IntegerEditor(caption="Partition number (1-4): ",
                                     default=1)
        self.size = StringEditor(
            caption="Size (max {}): ".format(
                _humanize_size(self.selected_disk.freespace)))
        self.mountpoint = StringEditor(caption="Mount: ", edit_text="/")
        self.fstype = Selector(opts=self.model.supported_filesystems)
        body = [
            Padding.center_95(
                Text("Adding partition to {}".format(
                    self.selected_disk.devpath))),
            Padding.line_break(""),
            Padding.center_90(self._container()),
            Padding.line_break(""),
            Padding.center_40(self._build_buttons())
        ]
        partition_box = Padding.center_65(Box(body))
        super().__init__(partition_box)

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button_secondary(cancel, focus_map='button_secondary focus'),
            Color.button_secondary(done, focus_map='button_secondary focus')
        ]
        return Pile(buttons)

    def _format_edit(self):
        formats_list = Pile(self.fstype.group)
        return Columns([(10, Text("Format: ")), formats_list], 2)

    def _container(self):
        total_items = [
            self.partnum,
            self.size,
            self._format_edit(),
            self.mountpoint
        ]

        return Pile(total_items)

    def cancel(self, button):
        self.signal.emit_signal('filesystem:show')

    def done(self, result):
        """ partition spec

        { 'partition_number': Int,
          'size': Int(M|G),
          'format' Str(ext4|btrfs..,
          'mount_point': Str
        }
        """
        result = {
            "partnum": self.partnum.value,
            "raw_size": self.size.value,
            "bytes": _dehumanize_size(self.size.value),
            "fstype": self.fstype.value,
            "mountpoint": self.mountpoint.value
        }
        log.debug("Add Partition Result: {}".format(result))
        self.signal.emit_signal(
            'filesystem:finish-add-disk-partition',
            self.selected_disk.devpath, result)


class DiskPartitionView(WidgetWrap):
    def __init__(self, model, signal, selected_disk):
        self.model = model
        self.signal = signal
        self.selected_disk = selected_disk
        self.disk_obj = self.model.get_disk(self.selected_disk)

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
        partitioned_disks = []

        for mnt, size, fstype, path in self.disk_obj.get_fs_table():
            mnt = Text(mnt)
            size = Text("{} GB".format(size))
            fstype = Text(fstype) if fstype else '-'
            path = Text(path) if path else '-'
            partition_column = Columns([
                (15, path),
                size,
                fstype,
                mnt
            ], 4)
            partitioned_disks.append(partition_column)
        free_space = str(_humanize_size(self.disk_obj.freespace))
        partitioned_disks.append(Columns([
            (15, Text("FREE SPACE")),
            Text(free_space),
            Text(""),
            Text("")
        ], 4))

        return BoxAdapter(SimpleList(partitioned_disks, is_selectable=False),
                          height=len(partitioned_disks))

    def _build_menu(self):
        """
        Builds the add partition menu with user visible
        changes to the button depending on if existing
        partitions exist or not.
        """
        return Pile([self.add_partition_w(), self.create_swap_w()])

    def create_swap_w(self):
        """ Handles presenting an enabled create swap on
        entire device button if no partition exists, otherwise
        it is disabled.
        """
        text = ("Format or create swap on entire "
                "device (unusual, advanced)")
        if len(self.model.get_partitions()) == 0:
            return Color.button_secondary(done_btn(label=text,
                                                   on_press=self.create_swap),
                                          focus_map='button_secondary focus')
        return Color.info_minor(Text(text))

    def add_partition_w(self):
        """ Handles presenting the add partition widget button
        depending on if partitions exist already or not.
        """
        text = "Add first GPT partition"
        if len(self.model.get_partitions()) > 0:
            text = "Add partition (max size {})".format(
                _humanize_size(self.disk_obj.freespace))
        return Color.button_secondary(done_btn(label=text,
                                               on_press=self.add_partition),
                                      focus_map='button_secondary focus')

    def add_partition(self, result):
        self.signal.emit_signal('filesystem:add-disk-partition',
                                self.selected_disk)

    def create_swap(self, result):
        self.signal.emit_signal('filesystem:create-swap-entire-device')

    def done(self, result):
        actions = self.disk_obj.get_actions()
        self.signal.emit_signal('filesystem:finish', False, actions)

    def cancel(self, button):
        self.signal.emit_signal('filesystem:show')


class FilesystemView(ViewPolicy):
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
        for dev in self.model.devices.values():
            for mnt, size, fstype, path in dev.get_fs_table():
                mnt = Text(mnt)
                size = Text("{} GB".format(size))
                fstype = Text(fstype) if fstype else '-'
                path = Text(path) if path else '-'
                partition_column = Columns([
                    (15, path),
                    size,
                    fstype,
                    mnt
                ], 4)
                pl.append(partition_column)
        return Pile(pl)

    def _build_buttons(self):
        buttons = [
            Color.button_secondary(reset_btn(on_press=self.cancel),
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
        for opt, sig, _ in self.model.get_menu():
            opts.append(
                Color.button_secondary(
                    done_btn(label=opt,
                             on_press=self.on_fs_menu_press),
                    focus_map='button_secondary focus'))
        return Pile(opts)

    def on_fs_menu_press(self, result):
        self.signal.emit_signal(
            self.model.get_signal_by_name(result.label))

    def cancel(self, button):
        self.signal.emit_signal(self.model.get_previous_signal)

    def reset(self, button):
        self.signal.emit_signal('filesystem:reset', True)

    def done(self, button):
        actions = self.model.get_actions()
        self.signal.emit_signal('filesystem:finish', False, actions)

    def show_disk_partition_view(self, partition):
        self.signal.emit_signal('filesystem:show-disk-partition',
                                partition.label)
