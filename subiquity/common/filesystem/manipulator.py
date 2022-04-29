# Copyright 2020 Canonical, Ltd.
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

from curtin.block import get_resize_fstypes

from subiquity.common.filesystem import boot, gaps
from subiquity.common.types import Bootloader
from subiquity.models.filesystem import (
    align_up,
    Partition,
    )

log = logging.getLogger('subiquity.common.filesystem.manipulator')


class FilesystemManipulator:

    def create_mount(self, fs, spec):
        if spec.get('mount') is None:
            return
        mount = self.model.add_mount(fs, spec['mount'])
        if self.model.needs_bootloader_partition():
            vol = fs.volume
            if vol.type == "partition" and boot.can_be_boot_device(vol.device):
                self.add_boot_disk(vol.device)
        return mount

    def delete_mount(self, mount):
        if mount is None:
            return
        self.model.remove_mount(mount)

    def create_filesystem(self, volume, spec):
        if spec.get('fstype') is None:
            # prep partitions are always wiped (and never have a filesystem)
            if getattr(volume, 'flag', None) != 'prep':
                volume.wipe = None
            fstype = volume.original_fstype()
            if fstype is None:
                return None
            preserve = True
        else:
            fstype = spec['fstype']
            volume.wipe = 'superblock'
            preserve = False
        fs = self.model.add_filesystem(volume, fstype, preserve)
        if isinstance(volume, Partition):
            if fstype == "swap":
                volume.flag = "swap"
            elif volume.flag == "swap":
                volume.flag = ""
        if spec.get('fstype') == "swap":
            self.model.add_mount(fs, "")
        if spec.get('fstype') is None and spec.get('use_swap'):
            self.model.add_mount(fs, "")
        self.create_mount(fs, spec)
        return fs

    def delete_filesystem(self, fs):
        if fs is None:
            return
        self.delete_mount(fs.mount())
        self.model.remove_filesystem(fs)
    delete_format = delete_filesystem

    def create_partition(self, device, gap, spec, **kw):
        if gap.in_extended:
            if kw.get('flag') is not None:
                raise Exception('oh no')
            kw['flag'] = 'logical'
        part = self.model.add_partition(
            device, size=spec["size"], offset=gap.offset, **kw)
        self.create_filesystem(part, spec)
        return part

    def delete_partition(self, part, override_preserve=False):
        if not override_preserve and part.device.preserve and \
                self.model.storage_version < 2:
            raise Exception("cannot delete partitions from preserved disks")
        self.clear(part)
        self.model.remove_partition(part)

    def create_raid(self, spec):
        for d in spec['devices'] | spec['spare_devices']:
            self.clear(d)
        raid = self.model.add_raid(
            spec['name'],
            spec['level'].value,
            spec['devices'],
            spec['spare_devices'])
        return raid

    def delete_raid(self, raid):
        if raid is None:
            return
        self.clear(raid)
        for v in raid._subvolumes:
            self.delete_raid(v)
        for p in list(raid.partitions()):
            self.delete_partition(p, True)
        for d in set(raid.devices) | set(raid.spare_devices):
            d.wipe = 'superblock'
        self.model.remove_raid(raid)

    def create_volgroup(self, spec):
        devices = set()
        key = spec.get('password')
        for device in spec['devices']:
            self.clear(device)
            if key:
                device = self.model.add_dm_crypt(device, key)
            devices.add(device)
        return self.model.add_volgroup(name=spec['name'], devices=devices)
    create_lvm_volgroup = create_volgroup

    def delete_volgroup(self, vg):
        for lv in list(vg.partitions()):
            self.delete_logical_volume(lv)
        for d in vg.devices:
            d.wipe = 'superblock'
            if d.type == "dm_crypt":
                self.model.remove_dm_crypt(d)
        self.model.remove_volgroup(vg)
    delete_lvm_volgroup = delete_volgroup

    def create_logical_volume(self, vg, spec):
        lv = self.model.add_logical_volume(
            vg=vg,
            name=spec['name'],
            size=spec['size'])
        self.create_filesystem(lv, spec)
        return lv
    create_lvm_partition = create_logical_volume

    def delete_logical_volume(self, lv):
        self.clear(lv)
        self.model.remove_logical_volume(lv)
    delete_lvm_partition = delete_logical_volume

    def delete(self, obj):
        if obj is None:
            return
        getattr(self, 'delete_' + obj.type)(obj)

    def clear(self, obj):
        if obj.type == "disk":
            obj.preserve = False
        obj.wipe = 'superblock'
        for subobj in obj.fs(), obj.constructed_device():
            self.delete(subobj)

    def reformat(self, disk, ptable=None):
        disk.grub_device = False
        if ptable is not None:
            disk.ptable = ptable
        for p in list(disk.partitions()):
            self.delete_partition(p, True)
        self.clear(disk)

    def can_resize_partition(self, partition):
        if not partition.preserve:
            return True
        if partition.format not in get_resize_fstypes():
            return False
        return True

    def partition_disk_handler(self, disk, spec, *, partition=None, gap=None):
        log.debug('partition_disk_handler: %s %s %s %s',
                  disk, spec, partition, gap)

        if partition is not None:
            if 'size' in spec and spec['size'] != partition.size:
                trailing, gap_size = \
                     gaps.movable_trailing_partitions_and_gap_size(partition)
                new_size = align_up(spec['size'])
                size_change = new_size - partition.size
                if size_change > gap_size:
                    raise Exception("partition size too large")
                if not self.can_resize_partition(partition):
                    raise Exception("partition cannot support resize")
                partition.size = new_size
                partition.resize = True
                for part in trailing:
                    part.offset += size_change
            self.delete_filesystem(partition.fs())
            self.create_filesystem(partition, spec)
            return

        if len(disk.partitions()) == 0:
            if disk.type == "disk":
                disk.preserve = False
                disk.wipe = 'superblock-recursive'
            elif disk.type == "raid":
                disk.wipe = 'superblock-recursive'

        needs_boot = self.model.needs_bootloader_partition()
        log.debug('model needs a bootloader partition? {}'.format(needs_boot))
        can_be_boot = boot.can_be_boot_device(disk)
        if needs_boot and len(disk.partitions()) == 0 and can_be_boot:
            self.add_boot_disk(disk)

            # adjust downward the partition size (if necessary) to accommodate
            # bios/grub partition.  It's OK and useful to assign a new gap:
            # 1) with len(partitions()) == 0 there could only have been 1 gap
            # 2) having just done add_boot_disk(), the gap is no longer valid.
            gap = gaps.largest_gap(disk)
            if spec['size'] > gap.size:
                log.debug(
                    "Adjusting request down from %s to %s",
                    spec['size'], gap.size)
                spec['size'] = gap.size

        self.create_partition(disk, gap, spec)

        log.debug("Successfully added partition")

    def logical_volume_handler(self, vg, spec, *, partition, gap):
        # keep the partition name for compat with PartitionStretchy.handler
        lv = partition

        log.debug('logical_volume_handler: %s %s %s', vg, lv, spec)

        if lv is not None:
            if 'name' in spec:
                lv.name = spec['name']
            if 'size' in spec:
                lv.size = align_up(spec['size'])
                if gaps.largest_gap_size(vg) < 0:
                    raise Exception("lv size too large")
            self.delete_filesystem(lv.fs())
            self.create_filesystem(lv, spec)
            return

        self.create_logical_volume(vg, spec)

    def add_format_handler(self, volume, spec):
        log.debug('add_format_handler %s %s', volume, spec)
        self.clear(volume)
        self.create_filesystem(volume, spec)

    def raid_handler(self, existing, spec):
        log.debug("raid_handler %s %s", existing, spec)
        if existing is not None:
            for d in existing.devices | existing.spare_devices:
                d._constructed_device = None
            for d in spec['devices'] | spec['spare_devices']:
                self.clear(d)
                d._constructed_device = existing
            existing.name = spec['name']
            existing.raidlevel = spec['level'].value
            existing.devices = spec['devices']
            existing.spare_devices = spec['spare_devices']
        else:
            self.create_raid(spec)

    def volgroup_handler(self, existing, spec):
        if existing is not None:
            key = spec.get('password')
            for d in existing.devices:
                if d.type == "dm_crypt":
                    self.model.remove_dm_crypt(d)
                    d = d.volume
                d._constructed_device = None
            devices = set()
            for d in spec['devices']:
                self.clear(d)
                if key:
                    d = self.model.add_dm_crypt(d, key)
                d._constructed_device = existing
                devices.add(d)
            existing.name = spec['name']
            existing.devices = devices
        else:
            self.create_volgroup(spec)

    def _mount_esp(self, part):
        if part.fs() is None:
            self.model.add_filesystem(part, 'fat32')
        self.model.add_mount(part.fs(), '/boot/efi')

    def remove_boot_disk(self, boot_disk):
        if self.model.bootloader == Bootloader.BIOS:
            boot_disk.grub_device = False
        partitions = [
            p for p in boot_disk.partitions()
            if boot.is_bootloader_partition(p)
            ]
        remount = False
        if boot_disk.preserve:
            if self.model.bootloader == Bootloader.BIOS:
                return
            for p in partitions:
                p.grub_device = False
                if self.model.bootloader == Bootloader.PREP:
                    p.wipe = None
                elif self.model.bootloader == Bootloader.UEFI:
                    if p.fs():
                        if p.fs().mount():
                            self.delete_mount(p.fs().mount())
                            remount = True
                        if not p.fs().preserve and p.original_fstype():
                            self.delete_filesystem(p.fs())
                            self.model.add_filesystem(
                                p, p.original_fstype(), preserve=True)
        else:
            full = gaps.largest_gap_size(boot_disk) == 0
            tot_size = 0
            for p in partitions:
                tot_size += p.size
                if p.fs() and p.fs().mount():
                    remount = True
                self.delete_partition(p)
            if full:
                largest_part = max(
                    boot_disk.partitions(), key=lambda p: p.size)
                largest_part.size += tot_size
        if self.model.bootloader == Bootloader.UEFI and remount:
            part = self.model._one(type='partition', grub_device=True)
            if part:
                self._mount_esp(part)

    def add_boot_disk(self, new_boot_disk):
        if not self.supports_resilient_boot:
            for disk in boot.all_boot_devices(self.model):
                self.remove_boot_disk(disk)
        boot.get_boot_device_plan(new_boot_disk).apply(self)
        if not new_boot_disk._has_preexisting_partition():
            if new_boot_disk.type == "disk":
                new_boot_disk.preserve = False
