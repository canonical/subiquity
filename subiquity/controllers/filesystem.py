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

from subiquitycore.controller import BaseController
from subiquitycore.ui.dummy import DummyView
from subiquitycore.ui.error import ErrorView

from subiquity.curtin import (
    CURTIN_CONFIGS,
    curtin_write_storage_actions,
    )
from subiquity.models import (FilesystemModel, RaidModel)
from subiquity.models.filesystem import humanize_size
from subiquity.ui.views import (
    AddFormatView,
    AddPartitionView,
    BcacheView,
    DiskInfoView,
    DiskPartitionView,
    FilesystemView,
    GuidedFilesystemView,
    LVMVolumeGroupView,
    RaidView,
    )


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
        self.model.probe()  # probe before we complete

    def default(self, reset=False):
        # FIXME: Is this the best way to zero out this list for a reset?
        if reset:
            log.info("Resetting Filesystem model")
            self.model.reset()

        title = "Filesystem setup"
        footer = ("XXX")
        self.ui.set_header(title)
        self.ui.set_footer(footer, 30)
        self.ui.set_body(GuidedFilesystemView(self.model, self))

    def manual(self):
        # FIXME: Is this the best way to zero out this list for a reset?
        title = "Filesystem setup"
        footer = ("Select available disks to format and mount")
        self.ui.set_header(title)
        self.ui.set_footer(footer, 30)
        self.ui.set_body(FilesystemView(self.model, self))

    def reset(self):
        log.info("Resetting Filesystem model")
        self.model.reset()
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

    def finish(self):
        log.info("Rendering curtin config from user choices")
        try:
            curtin_write_storage_actions(
                CURTIN_CONFIGS['storage'],
                actions=self.model.render())
        except PermissionError:
            log.exception('Failed to write storage actions')
            self.filesystem_error('curtin_write_storage_actions')
            return None

        log.info("Rendering preserved config for post install")
        preserved_actions = []
        for a in self.model.render():
            a['preserve'] = True
            preserved_actions.append(a)
        try:
            curtin_write_storage_actions(
                CURTIN_CONFIGS['preserved'],
                actions=preserved_actions)
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
    def partition_disk(self, disk):
        log.debug("In disk partition view, using {} as the disk.".format(disk.serial))
        title = ("Partition, format, and mount {}".format(disk.serial))
        footer = ("Partition the disk, or format the entire device "
                  "without partitions.")
        self.ui.set_header(title)
        self.ui.set_footer(footer)
        dp_view = DiskPartitionView(self.model, self, disk)

        self.ui.set_body(dp_view)

    def add_disk_partition(self, disk):
        log.debug("Adding partition to {}".format(disk))
        footer = ("Select whole disk, or partition, to format and mount.")
        self.ui.set_footer(footer)
        adp_view = AddPartitionView(self.model, self, disk)
        self.ui.set_body(adp_view)

    def add_disk_partition_handler(self, disk, spec):
        log.debug('spec: {}'.format(spec))
        log.debug('disk.freespace: {}'.format(disk.free))

        system_bootable = self.model.bootable()
        log.debug('model has bootable device? {}'.format(system_bootable))
        if not system_bootable and len(disk.partitions()) == 0:
            if self.is_uefi():
                log.debug('Adding EFI partition first')
                part = self.model.add_partition(disk=disk, partnum=1, size=UEFI_GRUB_SIZE_BYTES, flag='bios_grub')
                fs = self.model.add_filesystem(part, 'fat32')
                self.model.add_mount(fs, '/boot/efi')
            else:
                log.debug('Adding grub_bios gpt partition first')
                part = self.model.add_partition(disk=disk, partnum=1, size=BIOS_GRUB_SIZE_BYTES, flag='bios_grub')
            disk.grub_device = True

            # adjust downward the partition size to accommodate
            # the offset and bios/grub partition
            # XXX should probably only do this if the partition is now too big to fit on the disk?
            log.debug("Adjusting request down:" +
                      "{} - {} = {}".format(spec['bytes'], part.size,
                                            spec['bytes'] - part.size))
            spec['bytes'] -= part.size
            spec['partnum'] = 2

        part = self.model.add_partition(disk=disk, partnum=spec["partnum"], size=spec["bytes"])
        if spec['fstype'] is not None:
            fs = self.model.add_filesystem(part, spec['fstype'])
            if spec['mountpoint']:
                self.model.add_mount(fs, spec['mountpoint'])

        log.info("Successfully added partition")
        self.partition_disk(disk)

    def add_format_handler(self, volume, spec, back):
        log.debug('add_format_handler')
        if spec['fstype'] is not None:
            fs = self.model.add_filesystem(volume, spec['fstype'])
        else:
            fs = volume.fs()
        if spec['mountpoint']:
            if fs is None:
                raise Exception("{} is not formatted".format(volume.path))
            self.model.add_mount(fs, spec['mountpoint'])
        back()

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

    def create_volume_group(self, *args, **kwargs):
        title = ("Create Logical Volume Group (\"LVM2\") disk")
        footer = ("ENTER on a disk will show detailed "
                  "information for that disk")
        excerpt = ("Use SPACE to select disks to form your LVM2 volume group, "
                   "and then specify the Volume Group name. ")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(LVMVolumeGroupView(self.model, self.signal))

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

    def format_entire(self, disk):
        log.debug("format_entire {}".format(disk.serial))
        header = ("Format and/or mount {}".format(disk.serial))
        footer = ("Format or mount whole disk.")
        self.ui.set_header(header)
        self.ui.set_footer(footer)
        afv_view = AddFormatView(self.model, self, disk, lambda : self.partition_disk(disk))
        self.ui.set_body(afv_view)

    def format_mount_partition(self, partition):
        log.debug("format_entire {}".format(partition))
        if partition.fs() is not None:
            header = ("Mount partition {} of {}".format(partition.number, partition.device.serial))
            footer = ("Mount partition.")
        else:
            header = ("Format and mount partition {} of {}".format(partition.number, partition.device.serial))
            footer = ("Format and mount partition.")
        self.ui.set_header(header)
        self.ui.set_footer(footer)
        afv_view = AddFormatView(self.model, self, partition, self.default)
        self.ui.set_body(afv_view)

    def show_disk_information_next(self, disk):
        log.debug('show_disk_info_next: curr_device={}'.format(disk))
        available = self.model.all_disks()
        idx = available.index(disk)
        next_idx = (idx + 1) % len(available)
        next_device = available[next_idx]
        self.show_disk_information(next_device)

    def show_disk_information_prev(self, disk):
        log.debug('show_disk_info_prev: curr_device={}'.format(disk))
        available = self.model.all_disks()
        idx = available.index(disk)
        next_idx = (idx - 1) % len(available)
        next_device = available[next_idx]
        self.show_disk_information(next_device)

    def show_disk_information(self, disk):
        """ Show disk information, requires sudo/root
        """
        bus = disk._info.raw.get('ID_BUS', None)
        major = disk._info.raw.get('MAJOR', None)
        if bus is None and major == '253':
            bus = 'virtio'

        devpath = disk._info.raw.get('DEVPATH', disk.path)
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
            'devname': disk.path,
            'devpath': devpath,
            'model': disk.model,
            'serial': disk.serial,
            'size': disk.size,
            'humansize': humanize_size(disk.size),
            'vendor': disk._info.vendor,
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
        disk_info_view = DiskInfoView(self.model, self, disk, result)
        footer = ('Select next or previous disks with n and p')
        self.ui.set_footer(footer, 30)
        self.ui.set_body(disk_info_view)

    def is_uefi(self):
        if self.opts.dry_run and self.opts.uefi:
            log.debug('forcing is_uefi True beacuse of options')
            return True

        return os.path.exists('/sys/firmware/efi')
