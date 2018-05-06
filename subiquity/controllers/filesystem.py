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

from subiquity.models.filesystem import align_up, humanize_size
from subiquity.ui.views import (
    BcacheView,
    DiskInfoView,
    DiskPartitionView,
    FilesystemView,
    GuidedDiskSelectionView,
    GuidedFilesystemView,
    LVMVolumeGroupView,
    PartitionView,
    RaidView,
    )


log = logging.getLogger("subiquitycore.controller.filesystem")

BIOS_GRUB_SIZE_BYTES = 1 * 1024 * 1024   # 1MiB
UEFI_GRUB_SIZE_BYTES = 512 * 1024 * 1024  # 512MiB EFI partition


class FilesystemController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.filesystem
        self.answers = self.all_answers.get("Filesystem", {})
        self.answers.setdefault('guided', False)
        self.answers.setdefault('guided-index', 0)
        self.answers.setdefault('manual', False)
        # self.iscsi_model = IscsiDiskModel()
        # self.ceph_model = CephDiskModel()
        self.model.probe()  # probe before we complete

    def default(self):
        self.ui.set_body(GuidedFilesystemView(self))
        if self.answers['guided']:
            self.guided()
        elif self.answers['manual']:
            self.manual()

    def manual(self):
        self.ui.set_body(FilesystemView(self.model, self))
        if self.answers['guided']:
            self.finish()

    def guided(self):
        v = GuidedDiskSelectionView(self.model, self)
        self.ui.set_body(v)
        if self.answers['guided']:
            index = self.answers['guided-index']
            disk = self.model.all_disks()[index]
            v.choose_disk(None, disk)

    def reset(self):
        log.info("Resetting Filesystem model")
        self.model.reset()
        self.manual()

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def finish(self):
        # start curtin install in background
        self.signal.emit_signal('installprogress:filesystem-config-done')
        # switch to next screen
        self.signal.emit_signal('next-screen')

    # Filesystem/Disk partition -----------------------------------------------
    def partition_disk(self, disk):
        log.debug("In disk partition view, using {} as the disk.".format(disk.label))
        dp_view = DiskPartitionView(self.model, self, disk)

        self.ui.set_body(dp_view)

    def add_disk_partition(self, disk):
        log.debug("Adding partition to {}".format(disk))
        adp_view = PartitionView(self.model, self, disk)
        self.ui.set_body(adp_view)

    def edit_partition(self, disk, partition):
        log.debug("Editing partition {}".format(partition))
        adp_view = PartitionView(self.model, self, disk, partition)
        self.ui.set_body(adp_view)

    def delete_partition(self, part):
        old_fs = part.fs()
        if old_fs is not None:
            self.model._filesystems.remove(old_fs)
            part._fs = None
            mount = old_fs.mount()
            if mount is not None:
                old_fs._mount = None
                self.model._mounts.remove(mount)
        part.device.partitions().remove(part)
        self.model._partitions.remove(part)
        self.partition_disk(part.device)

    def partition_disk_handler(self, disk, partition, spec):
        log.debug('spec: {}'.format(spec))
        log.debug('disk.freespace: {}'.format(disk.free))

        if partition is not None:
            partition.size = align_up(spec['size'])
            if disk.free < 0:
                raise Exception("partition size too large")
            old_fs = partition.fs()
            if old_fs is not None:
                self.model._filesystems.remove(old_fs)
                partition._fs = None
                mount = old_fs.mount()
                if mount is not None:
                    old_fs._mount = None
                    self.model._mounts.remove(mount)
            if spec['fstype'].label is not None:
                fs = self.model.add_filesystem(partition, spec['fstype'].label)
                if spec['mount']:
                  self.model.add_mount(fs, spec['mount'])
            self.manual()
            return

        system_bootable = self.model.bootable()
        log.debug('model has bootable device? {}'.format(system_bootable))
        if not system_bootable and len(disk.partitions()) == 0:
            if self.is_uefi():
                part_size = UEFI_GRUB_SIZE_BYTES
                if UEFI_GRUB_SIZE_BYTES*2 >= disk.size:
                    part_size = disk.size // 2
                log.debug('Adding EFI partition first')
                part = self.model.add_partition(disk=disk, size=part_size, flag='boot')
                fs = self.model.add_filesystem(part, 'fat32')
                self.model.add_mount(fs, '/boot/efi')
            else:
                log.debug('Adding grub_bios gpt partition first')
                part = self.model.add_partition(disk=disk, size=BIOS_GRUB_SIZE_BYTES, flag='bios_grub')
            disk.grub_device = True

            # adjust downward the partition size (if necessary) to accommodate
            # bios/grub partition
            if spec['size'] > disk.free:
                log.debug("Adjusting request down:" +
                        "{} - {} = {}".format(spec['size'], part.size,
                                                disk.free))
                spec['size'] = disk.free

        part = self.model.add_partition(disk=disk, size=spec["size"])
        if spec['fstype'].label is not None:
            fs = self.model.add_filesystem(part, spec['fstype'].label)
            if spec['mount']:
                self.model.add_mount(fs, spec['mount'])

        log.info("Successfully added partition")
        self.manual()

    def add_format_handler(self, volume, spec, back):
        log.debug('add_format_handler')
        old_fs = volume.fs()
        if old_fs is not None:
            self.model._filesystems.remove(old_fs)
            volume._fs = None
            mount = old_fs.mount()
            if mount is not None:
                old_fs._mount = None
                self.model._mounts.remove(mount)
        if spec['fstype'].label is not None:
            fs = self.model.add_filesystem(volume, spec['fstype'].label)
            if spec['mount']:
                self.model.add_mount(fs, spec['mount'])
        back()

    def make_boot_disk(self, disk):
        for p in self.model._partitions:
            if p.flag in ("bios_grub", "boot"):
                full = p.device.free == 0
                p.device._partitions.remove(p)
                if full:
                    largest_part = max((part.size, part) for part in p.device._partitions)[1]
                    largest_part.size += p.size
                if disk.free < p.size:
                    largest_part = max((part.size, part) for part in disk._partitions)[1]
                    largest_part.size -= (p.size - disk.free)
                disk._partitions.insert(0, p)
                p.device = disk
        self.partition_disk(disk)

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
        log.debug("format_entire {}".format(disk.label))
        afv_view = FormatEntireView(self.model, self, disk, lambda : self.partition_disk(disk))
        self.ui.set_body(afv_view)

    def format_mount_partition(self, partition):
        log.debug("format_mount_partition {}".format(partition))
        afv_view = FormatEntireView(self.model, self, partition, self.manual)
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
        if dinfo['serial'] is None:
            dinfo['serial'] = 'unknown'
        if dinfo['model'] is None:
            dinfo['model'] = 'unknown'
        if dinfo['vendor'] is None:
            dinfo['vendor'] = 'unknown'

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
        self.ui.set_body(disk_info_view)

    def is_uefi(self):
        if self.opts.dry_run:
            return self.opts.uefi

        return os.path.exists('/sys/firmware/efi')
