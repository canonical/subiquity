# Copyright 2021 Canonical, Ltd.
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

import attr
import functools

from subiquity.common.filesystem import gaps
from subiquity.models.filesystem import (
    Disk,
    Raid,
    Bootloader,
    Partition,
    )


@functools.singledispatch
def is_boot_device(device):
    """Is `device` a boot device?"""
    return False


@is_boot_device.register(Disk)
def _is_boot_device_disk(disk):
    bl = disk._m.bootloader
    if bl == Bootloader.NONE:
        return False
    elif bl == Bootloader.BIOS:
        return disk.grub_device
    elif bl in [Bootloader.PREP, Bootloader.UEFI]:
        return any(p.grub_device for p in disk._partitions)


@is_boot_device.register(Raid)
def _is_boot_device_raid(raid):
    bl = raid._m.bootloader
    if bl != Bootloader.UEFI:
        return False
    if not raid.container or raid.container.metadata != 'imsm':
        return False
    return any(p.grub_device for p in raid._partitions)


@functools.singledispatch
def can_be_boot_device(device, *, with_reformatting=False):
    """Can `device` be made into a boot device?

    If with_reformatting=True, return true if the device can be made
    into a boot device after reformatting.
    """
    return False


@can_be_boot_device.register(Disk)
def _can_be_boot_device_disk(disk, *, with_reformatting=False):
    bl = disk._m.bootloader
    if disk._has_preexisting_partition() and not with_reformatting:
        if bl == Bootloader.BIOS:
            if disk.ptable == "msdos":
                return True
            else:
                return disk._partitions[0].flag == "bios_grub"
        elif bl == Bootloader.UEFI:
            return any(is_esp(p) for p in disk._partitions)
        elif bl == Bootloader.PREP:
            return any(p.flag == "prep" for p in disk._partitions)
    else:
        return True


@can_be_boot_device.register(Raid)
def _can_be_boot_device_raid(raid, *, with_reformatting=False):
    bl = raid._m.bootloader
    if bl != Bootloader.UEFI:
        return False
    if not raid.container or raid.container.metadata != 'imsm':
        return False
    if raid._has_preexisting_partition() and not with_reformatting:
        return any(is_esp(p) for p in raid._partitions)
    else:
        return True


@functools.singledispatch
def is_esp(device):
    """Is `device` a UEFI ESP?"""
    return False


@is_esp.register(Partition)
def _is_esp_partition(partition):
    if not can_be_boot_device(partition.device, with_reformatting=True):
        return False
    if partition.device.ptable == "gpt":
        return partition.flag == "boot"
    elif isinstance(partition.device, Disk):
        blockdev_raw = partition._m._probe_data['blockdev'].get(
            partition._path())
        if blockdev_raw is None:
            return False
        typecode = blockdev_raw.get("ID_PART_ENTRY_TYPE")
        if typecode is None:
            return False
        try:
            return int(typecode, 0) == 0xef
        except ValueError:
            # In case there was garbage in the udev entry...
            return False
    else:
        return False


def all_boot_devices(model):
    """Return all current boot devices for `model`."""
    candidates = model.all_disks() + model.all_raids()
    return [cand for cand in candidates if is_boot_device(cand)]


def is_bootloader_partition(partition):
    if partition._m.bootloader == Bootloader.BIOS:
        return partition.flag == "bios_grub"
    elif partition._m.bootloader == Bootloader.UEFI:
        return is_esp(partition)
    elif partition._m.bootloader == Bootloader.PREP:
        return partition.flag == "prep"
    else:
        return False


@attr.s(auto_attribs=True)
class ResizePlan:
    part: object = None
    offset_delta: int = 0
    size_delta: int = 0
    gap_offset: int = 0
    gap_size: int = 0

    def apply(self):
        if self.part is None:
            return
        self.part.offset += self.part.offset_delta
        self.part.size -= self.part.size_delta

    def gap(self, device):
        return gaps.Gap(device, self.gap_offset, self.gap_size)


def resize_plan_for_size(self, disk, part_size):
    plan = ResizePlan()
    parts_and_gaps = gaps.parts_and_gaps(disk)

    for pg in parts_and_gaps:
        if isinstance(pg, gaps.Gap):
            if pg.size >= part_size:
                plan.gap_offset = pg.offset
                plan.gap_size = pg.size
                return plan

    new_parts = [p for p in disk.partitions() if not p.preserve]
    part = plan.part = max(new_parts, key=lambda p: p.size)
    plan.gap_offset = part.offset
    plan.gap_size = part_size
    needed = part_size

    largest_i = parts_and_gaps.index(part)

    if largest_i - 1 >= 0:
        preceding = parts_and_gaps[largest_i - 1]
        if isinstance(preceding, gaps.Gap):
            plan.gap_offset = preceding.offset
            needed -= preceding.size

    if largest_i + 1 < len(parts_and_gaps):
        trailing = parts_and_gaps[largest_i + 1]
        if isinstance(trailing, gaps.Gap):
            move_amount = min(trailing.size, needed)
            plan.offset_delta = move_amount
            needed -= move_amount

    if needed == 0:
        return plan
    elif needed > 0 and needed < part.size//2:
        plan.offset_delta += needed
        plan.size_delta -= needed
        return plan
    else:
        return None


def resize_plan_for_bios_grub(disk):
    pass
