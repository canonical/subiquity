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

from subiquity.models.filesystem import align_up
from subiquity.ui.views import (
    FilesystemView,
    GuidedDiskSelectionView,
    GuidedFilesystemView,
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

    def create_mount(self, fs, spec):
        if spec['mount'] is None:
            return
        mount = self.model.add_mount(fs, spec['mount'])
        return mount

    def delete_mount(self, mount):
        if mount is None:
            return
        self.model.remove_mount(mount)

    def create_filesystem(self, volume, spec):
        if spec['fstype'] is None:
            return
        fs = self.model.add_filesystem(volume, spec['fstype'].label)
        self.create_mount(fs, spec)
        return fs

    def delete_filesystem(self, fs):
        if fs is None:
            return
        self.delete_mount(fs.mount())
        self.model.remove_filesystem(fs)

    def create_partition(self, device, spec, flag=""):
        part = self.model.add_partition(device, spec["size"], flag)
        self.create_filesystem(part, spec)
        return part

    def delete_partition(self, part):
        self.delete_filesystem(part.fs())
        self.model.remove_partition(part)

    def partition_disk_handler(self, disk, partition, spec):
        log.debug('partition_disk_handler: %s %s %s', disk, partition, spec)
        log.debug('disk.freespace: {}'.format(disk.free))

        if partition is not None:
            partition.size = align_up(spec['size'])
            if disk.free < 0:
                raise Exception("partition size too large")
            self.delete_filesystem(partition.fs())
            self.create_filesystem(partition, spec)
            return

        system_bootable = self.model.bootable()
        log.debug('model has bootable device? {}'.format(system_bootable))
        if not system_bootable and len(disk.partitions()) == 0:
            if self.is_uefi():
                part_size = UEFI_GRUB_SIZE_BYTES
                if UEFI_GRUB_SIZE_BYTES*2 >= disk.size:
                    part_size = disk.size // 2
                log.debug('Adding EFI partition first')
                part = self.create_partition(
                    disk,
                    dict(
                        size=part_size,
                        fstype=self.model.fs_by_name['fat32'],
                        mount='/boot/efi'),
                    flag="boot")
            else:
                log.debug('Adding grub_bios gpt partition first')
                part = self.create_partition(
                    disk,
                    dict(
                        size=BIOS_GRUB_SIZE_BYTES,
                        fstype=None,
                        mount=None),
                    flag='bios_grub')
            disk.grub_device = True

            # adjust downward the partition size (if necessary) to accommodate
            # bios/grub partition
            if spec['size'] > disk.free:
                log.debug("Adjusting request down:" +
                          "{} - {} = {}".format(spec['size'], part.size,
                                                disk.free))
                spec['size'] = disk.free

        part = self.create_partition(disk, spec)

        log.info("Successfully added partition")

    def add_format_handler(self, volume, spec):
        log.debug('add_format_handler %s %s', volume, spec)
        self.delete_filesystem(volume.fs())
        self.create_filesystem(volume, spec)

    def make_boot_disk(self, disk):
        # XXX This violates abstractions, needs some thinking.
        for p in self.model._partitions:
            if p.flag in ("bios_grub", "boot"):
                full = p.device.free == 0
                p.device._partitions.remove(p)
                if full:
                    largest_part = max((part.size, part)
                                       for part in p.device._partitions)[1]
                    largest_part.size += p.size
                if disk.free < p.size:
                    largest_part = max((part.size, part)
                                       for part in disk._partitions)[1]
                    largest_part.size -= (p.size - disk.free)
                disk._partitions.insert(0, p)
                p.device = disk
        self.partition_disk(disk)

    def is_uefi(self):
        if self.opts.dry_run:
            return self.opts.uefi

        return os.path.exists('/sys/firmware/efi')
