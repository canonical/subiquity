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

import functools

import attr

from subiquity.models.filesystem import (
    align_up,
    align_down,
    Bootloader,
    Disk,
    LVM_CHUNK_SIZE,
    LVM_VolGroup,
    GPT_OVERHEAD,
    Partition,
    Raid,
    )

from subiquity.common.filesystem.manipulator import (
    BIOS_GRUB_SIZE_BYTES,
    get_efi_size,
    PREP_GRUB_SIZE_BYTES,
)


@attr.s(auto_attribs=True)
class Gap:
    device: object
    offset: int
    size: int
    type: str = 'gap'

    @property
    def id(self):
        return 'gap-' + self.device.id


@functools.singledispatch
def parts_and_gaps(device):
    raise NotImplementedError(device)


@parts_and_gaps.register(Disk)
@parts_and_gaps.register(Raid)
def parts_and_gaps_disk(device):
    if device._fs is not None:
        return []
    r = []
    used = 0
    for p in device.partitions():
        used = align_up(used + p.size, 1 << 20)
        r.append(p)
    if device.ptable == 'vtoc' and len(device._partitions) >= 3:
        return r
    end = align_down(device.size, 1 << 20) - GPT_OVERHEAD
    if end - used >= (1 << 20):
        r.append(Gap(device, used, end - used))
    return r


@parts_and_gaps.register(LVM_VolGroup)
def _parts_and_gaps_vg(device):
    used = 0
    r = []
    for lv in device._partitions:
        r.append(lv)
        used += lv.size
    if device.preserve:
        return r
    remaining = align_down(device.size - used, LVM_CHUNK_SIZE)
    if remaining >= LVM_CHUNK_SIZE:
        r.append(Gap(device, None, remaining))
    return r


def largest_gap(device):
    largest_size = 0
    largest = None
    for pg in parts_and_gaps(device):
        if isinstance(pg, Gap):
            if pg.size > largest_size:
                largest = pg
                largest_size = pg.size
    return largest


def largest_gap_size(device):
    largest = largest_gap(device)
    if largest is not None:
        return largest.size
    return 0


def trailing_gap(part):
    pgs = parts_and_gaps(part.device)
    for pg in pgs[pgs.index(part)+1:]:
        if isinstance(pg, Gap):
            return pg
        if pg.preserve:
            return None
    return None


def trailing_gap_size(part):
    g = trailing_gap(part)
    if g is not None:
        return g.size
    return 0


def _can_fit_bootloader_partition_bios(disk):
    for pg in parts_and_gaps(disk):
        if isinstance(pg, Partition):
            if pg.preserve:
                return False
            elif BIOS_GRUB_SIZE_BYTES - trailing_gap_size(pg) < pg.size//2:
                return True
        if isinstance(pg, Gap) and pg.size >= BIOS_GRUB_SIZE_BYTES:
            return True


def _can_fit_bootloader_partition_of_size(disk, size):
    for pg in parts_and_gaps(disk):
        if isinstance(pg, Partition):
            if pg.preserve:
                continue
            elif size - trailing_gap_size(pg) < pg.size//2:
                return True
        if isinstance(pg, Gap) and pg.size >= size:
            return True


def can_fit_bootloader_partition(disk):
    bl = disk._m.bootloader
    if bl == Bootloader.BIOS:
        return _can_fit_bootloader_partition_bios(disk)
    elif bl == Bootloader.UEFI:
        return _can_fit_bootloader_partition_of_size(
            disk, get_efi_size(disk))
    elif bl == Bootloader.PREP:
        return _can_fit_bootloader_partition_of_size(
            disk, PREP_GRUB_SIZE_BYTES)
