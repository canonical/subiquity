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
import os

from subiquitycore.controller import BaseController, view
from subiquitycore.ui.dummy import DummyView
from subiquitycore.ui.error import ErrorView

from subiquity.curtin import (curtin_write_storage_actions,
                              curtin_write_preserved_actions)
from subiquity.models.actions import preserve_action
from subiquity.models import (FilesystemModel, RaidModel)
from subiquity.models.filesystem import (_humanize_size)
from subiquity.ui.views import (DiskPartitionView, AddPartitionView,
                                AddFormatView, FilesystemView,
                                DiskInfoView, RaidView, BcacheView,
                                LVMVolumeGroupView)


log = logging.getLogger("subiquitycore.controller.filesystem")

BIOS_GRUB_SIZE_BYTES = 2 * 1024 * 1024   # 2MiB
UEFI_GRUB_SIZE_BYTES = 512 * 1024 * 1024  # 512MiB EFI partition


class FilesystemController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = FilesystemModel(self.prober, self.opts)
        # self.iscsi_model = IscsiDiskModel()
        # self.ceph_model = CephDiskModel()
        self.raid_model = RaidModel()

    @view
    def default(self, reset=False):
        # FIXME: Is this the best way to zero out this list for a reset?
        if reset:
            log.info("Resetting Filesystem model")
            self.model.reset()

        title = "Filesystem setup"
        footer = ("Select available disks to format and mount")
        self.ui.set_header(title)
        self.ui.set_footer(footer, 30)
        self.ui.set_body(FilesystemView(self.model, self))

    def reset(self):
        log.info("Resetting Filesystem model")
        self.model.reset()
        self.view_stack = []
        self.default()

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def filesystem_error(self, error_fname):
        title = "Filesystem error"
        footer = ("Error while installing Ubuntu")
        error_msg = "Failed to obtain write permissions to /tmp"
        self.ui.set_header(title)
        self.ui.set_footer(footer, 30)
        self.ui.set_body(ErrorView(self.signal, error_msg))

    def finish(self, actions):
        log.info("Rendering curtin config from user choices")
        try:
            curtin_write_storage_actions(actions=actions)
        except PermissionError:
            log.exception('Failed to write storage actions')
            self.filesystem_error('curtin_write_storage_actions')
            return None

        log.info("Rendering preserved config for post install")
        preserved_actions = [preserve_action(a) for a in actions]
        try:
            curtin_write_preserved_actions(actions=preserved_actions)
        except PermissionError:
            log.exception('Failed to write preserved actions')
            self.filesystem_error('curtin_write_preserved_actions')
            return None

        # mark that we've writting out curtin config
        self.signal.emit_signal('installprogress:wrote-install')

        # start curtin install in background
        self.signal.emit_signal('installprogress:curtin-install')

        # switch to next screen
        self.signal.emit_signal('next-screen')

    # Filesystem/Disk partition -----------------------------------------------
    @view
    def disk_partition(self, disk):
        log.debug("In disk partition view, using {} as the disk.".format(disk))
        title = ("Partition, format, and mount {}".format(disk))
        footer = ("Partition the disk, or format the entire device "
                  "without partitions.")
        self.ui.set_header(title)
        self.ui.set_footer(footer)
        dp_view = DiskPartitionView(self.model, self, disk)

        self.ui.set_body(dp_view)

    def disk_partition_handler(self, spec=None):
        log.debug("Disk partition: {}".format(spec))
        if spec is None:
            self.signal.prev_signal()
        self.disk_partition([])

    @view
    def add_disk_partition(self, disk):
        log.debug("Adding partition to {}".format(disk))
        footer = ("Select whole disk, or partition, to format and mount.")
        self.ui.set_footer(footer)
        adp_view = AddPartitionView(self.model, self, disk)
        self.ui.set_body(adp_view)

    def add_disk_partition_handler(self, disk, spec):
        current_disk = self.model.get_disk(disk)
        log.debug('spec: {}'.format(spec))
        log.debug('disk.freespace: {}'.format(current_disk.freespace))

        try:
            ''' create a gpt boot partition if one doesn't exist, only
                one one disk'''

            system_bootable = self.model.bootable()
            log.debug('model has bootable device? {}'.format(system_bootable))
            if system_bootable is False and \
               current_disk.parttype == 'gpt' and \
               len(current_disk.disk.partitions) == 0:
                if self.is_uefi():
                    log.debug('Adding EFI partition first')
                    size_added = \
                        current_disk.add_partition(partnum=1,
                                                   size=UEFI_GRUB_SIZE_BYTES,
                                                   flag='bios_grub',
                                                   fstype='fat32',
                                                   mountpoint='/boot/efi')
                else:
                    log.debug('Adding grub_bios gpt partition first')
                    size_added = \
                        current_disk.add_partition(partnum=1,
                                                   size=BIOS_GRUB_SIZE_BYTES,
                                                   fstype=None,
                                                   flag='bios_grub')
                current_disk.set_tag('(boot)')

                # adjust downward the partition size to accommodate
                # the offset and bios/grub partition
                log.debug("Adjusting request down:" +
                          "{} - {} = {}".format(spec['bytes'], size_added,
                                                spec['bytes'] - size_added))
                spec['bytes'] -= size_added
                spec['partnum'] = 2

            if spec["fstype"] in ["swap"]:
                current_disk.add_partition(partnum=spec["partnum"],
                                           size=spec["bytes"],
                                           fstype=spec["fstype"])
            else:
                current_disk.add_partition(partnum=spec["partnum"],
                                           size=spec["bytes"],
                                           fstype=spec["fstype"],
                                           mountpoint=spec["mountpoint"])
        except Exception:
            log.exception('Failed to add disk partition')
            log.debug('Returning to add-disk-partition')
            # FIXME: on failure, we should repopulate input values
            self.add_disk_partition(disk)

        log.info("Successfully added partition")

        log.debug("FS Table: {}".format(current_disk.get_fs_table()))
        self.prev_view()

    def add_disk_format_handler(self, disk, spec):
        log.debug('add_disk_format_handler')
        current_disk = self.model.get_disk(disk)
        log.debug('format spec: {}'.format(spec))
        log.debug('disk.freespace: {}'.format(current_disk.freespace))
        current_disk.format_device(spec['fstype'], spec['mountpoint'])
        log.debug("FS Table: {}".format(current_disk.get_fs_table()))
        self.prev_view()

    def connect_iscsi_disk(self, *args, **kwargs):
        # title = ("Disk and filesystem setup")
        # excerpt = ("Connect to iSCSI cluster")
        # self.ui.set_header(title, excerpt)
        # self.ui.set_footer("")
        # self.ui.set_body(IscsiDiskView(self.iscsi_model,
        #                                self.signal))
        self.ui.set_body(DummyView(self.signal))

    def connect_ceph_disk(self, *args, **kwargs):
        # title = ("Disk and filesystem setup")
        # footer = ("Select available disks to format and mount")
        # excerpt = ("Connect to Ceph storage cluster")
        # self.ui.set_header(title, excerpt)
        # self.ui.set_footer(footer)
        # self.ui.set_body(CephDiskView(self.ceph_model,
        #                               self.signal))
        self.ui.set_body(DummyView(self.signal))

    @view
    def create_volume_group(self, *args, **kwargs):
        title = ("Create Logical Volume Group (\"LVM2\") disk")
        footer = ("ENTER on a disk will show detailed "
                  "information for that disk")
        excerpt = ("Use SPACE to select disks to form your LVM2 volume group, "
                   "and then specify the Volume Group name. ")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(LVMVolumeGroupView(self.model, self.signal))

    @view
    def create_raid(self, *args, **kwargs):
        title = ("Create software RAID (\"MD\") disk")
        footer = ("ENTER on a disk will show detailed "
                  "information for that disk")
        excerpt = ("Use SPACE to select disks to form your RAID array, "
                   "and then specify the RAID parameters. Multiple-disk "
                   "arrays work best when all the disks in an array are "
                   "the same size and speed.")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(RaidView(self.model,
                                  self.signal))

    @view
    def create_bcache(self, *args, **kwargs):
        title = ("Create hierarchical storage (\"bcache\") disk")
        footer = ("ENTER on a disk will show detailed "
                  "information for that disk")
        excerpt = ("Use SPACE to select a cache disk and a backing disk"
                   " to form your bcache device.")

        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(BcacheView(self.model,
                                    self.signal))

    def add_raid_dev(self, result):
        log.debug('add_raid_dev: result={}'.format(result))
        self.model.add_raid_device(result)
        self.signal.prev_signal()

    def add_first_gpt_partition(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    @view
    def create_swap_entire_device(self, disk):
        log.debug('create_swap_entire_device')
        log.debug("formatting whole {}".format(disk))
        footer = ("Format or mount whole disk.")
        self.ui.set_footer(footer)
        afv_view = AddFormatView(self.model, self, disk)
        self.ui.set_body(afv_view)

    def show_disk_information_next(self, curr_device):
        log.debug('show_disk_info_next: curr_device={}'.format(curr_device))
        available = self.model.get_available_disk_names()
        idx = available.index(curr_device)
        next_idx = (idx + 1) % len(available)
        next_device = available[next_idx]
        self.show_disk_information(next_device)

    def show_disk_information_prev(self, curr_device):
        log.debug('show_disk_info_prev: curr_device={}'.format(curr_device))
        available = self.model.get_available_disk_names()
        idx = available.index(curr_device)
        next_idx = (idx - 1) % len(available)
        next_device = available[next_idx]
        self.show_disk_information(next_device)

    def show_disk_information(self, device):
        """ Show disk information, requires sudo/root
        """
        disk_info = self.model.get_disk_info(device)
        disk = self.model.get_disk(device)

        bus = disk_info.raw.get('ID_BUS', None)
        major = disk_info.raw.get('MAJOR', None)
        if bus is None and major == '253':
            bus = 'virtio'

        devpath = disk_info.raw.get('DEVPATH', disk.devpath)
        rotational = '1'
        try:
            dev = os.path.basename(devpath)
            rfile = '/sys/class/block/{}/queue/rotational'.format(dev)
            rotational = open(rfile, 'r').read().strip()
        except (PermissionError, FileNotFoundError, IOError):
            log.exception('WARNING: Failed to read file {}'.format(rfile))
            pass

        dinfo = {
            'bus': bus,
            'devname': disk.devpath,
            'devpath': devpath,
            'model': disk.model,
            'serial': disk.serial,
            'size': disk.size,
            'humansize': _humanize_size(disk.size),
            'vendor': disk_info.vendor,
            'rotational': 'true' if rotational == '1' else 'false',
        }

        template = """\n
{devname}:\n
 Vendor: {vendor}
 Model: {model}
 SerialNo: {serial}
 Size: {humansize} ({size}B)
 Bus: {bus}
 Rotational: {rotational}
 Path: {devpath}
"""
        result = template.format(**dinfo)
        log.debug('calling DiskInfoView()')
        disk_info_view = DiskInfoView(self.model, self, device, result)
        footer = ('Select next or previous disks with n and p')
        self.ui.set_footer(footer, 30)
        self.ui.set_body(disk_info_view)

    def is_uefi(self):
        if self.opts.dry_run and self.opts.uefi:
            log.debug('forcing is_uefi True beacuse of options')
            return True

        return os.path.exists('/sys/firmware/efi')
