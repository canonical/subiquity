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
from typing import List, Tuple

import attr

from subiquity.common.types import GapUsable
from subiquity.models.filesystem import (
    LVM_CHUNK_SIZE,
    Disk,
    LVM_LogicalVolume,
    LVM_VolGroup,
    Partition,
    Raid,
    align_down,
    align_up,
)


# should also set on_setattr=None with attrs 20.1.0
@attr.s(auto_attribs=True, frozen=True)
class Gap:
    device: object
    offset: int
    size: int
    in_extended: bool = False
    usable: str = GapUsable.YES

    type: str = "gap"

    @property
    def id(self):
        return "gap-" + self.device.id

    @property
    def is_usable(self):
        return self.usable == GapUsable.YES

    def split(self, size):
        """returns a tuple of two new gaps, split from the current gap based on
        the supplied size.  If size is equal to the gap size, the second gap is
        None.  The original gap is unmodified."""
        if size > self.size:
            raise ValueError("requested size larger than gap")
        if size == self.size:
            return (self, None)
        first_gap = Gap(
            device=self.device,
            offset=self.offset,
            size=size,
            in_extended=self.in_extended,
            usable=self.usable,
        )
        if self.in_extended:
            size += self.device.alignment_data().ebr_space
        rest_gap = Gap(
            device=self.device,
            offset=self.offset + size,
            size=self.size - size,
            in_extended=self.in_extended,
            usable=self.usable,
        )
        return (first_gap, rest_gap)

    def within(self):
        """Find the first gap that is contained wholly inside this gap."""
        gap_end = self.offset + self.size
        for pg in parts_and_gaps(self.device):
            if isinstance(pg, Gap):
                pg_end = pg.offset + pg.size
                if pg.offset >= self.offset and pg_end <= gap_end:
                    return pg
        return None


@functools.singledispatch
def parts_and_gaps(device):
    raise NotImplementedError(device)


def remaining_primary_partitions(device, info):
    primaries = [p for p in device.partitions() if not p.is_logical]
    return info.primary_part_limit - len(primaries)


def find_disk_gaps_v1(device):
    r = []
    used = 0
    info = device.alignment_data()
    used += info.min_start_offset
    for p in device._partitions:
        used = align_up(used + p.size, 1 << 20)
        r.append(p)
    if device._has_preexisting_partition():
        return r
    if remaining_primary_partitions(device, info) < 1:
        return r
    end = align_down(device.size - info.min_end_offset, 1 << 20)
    if end - used >= (1 << 20):
        r.append(Gap(device, used, end - used))
    return r


def find_disk_gaps_v2(device, info=None):
    result = []
    extended_end = None

    if info is None:
        info = device.alignment_data()

    def au(v):  # au == "align up"
        r = v % info.part_align
        if r:
            return v + info.part_align - r
        else:
            return v

    def ad(v):  # ad == "align down"
        return v - v % info.part_align

    def maybe_add_gap(start, end, in_extended):
        if in_extended or primary_parts_remaining > 0:
            usable = GapUsable.YES
        else:
            usable = GapUsable.TOO_MANY_PRIMARY_PARTS
        if end - start >= info.min_gap_size:
            result.append(
                Gap(
                    device=device,
                    offset=start,
                    size=end - start,
                    in_extended=in_extended,
                    usable=usable,
                )
            )

    prev_end = info.min_start_offset

    parts = device.partitions_by_offset()
    extended_end = None
    primary_parts_remaining = remaining_primary_partitions(device, info)

    for part in parts + [None]:
        if part is None:
            gap_end = ad(device.size - info.min_end_offset)
        else:
            if part.is_logical:
                gap_end = ad(part.offset - info.ebr_space)
            else:
                gap_end = ad(part.offset)

        gap_start = au(prev_end)

        if extended_end is not None:
            gap_start = min(extended_end, au(gap_start + info.ebr_space))

        if extended_end is not None and gap_end >= extended_end:
            maybe_add_gap(gap_start, ad(extended_end), True)
            maybe_add_gap(au(extended_end), gap_end, False)
            extended_end = None
        else:
            maybe_add_gap(gap_start, gap_end, extended_end is not None)

        if part is None:
            break

        result.append(part)

        if part.flag == "extended":
            prev_end = part.offset
            extended_end = part.offset + part.size
        else:
            prev_end = part.offset + part.size

    return result


@parts_and_gaps.register(Disk)
@parts_and_gaps.register(Raid)
def parts_and_gaps_disk(device):
    if device._fs is not None:
        return []
    if device._m.storage_version == 1:
        return find_disk_gaps_v1(device)
    else:
        return find_disk_gaps_v2(device)


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
        r.append(Gap(device, 0, remaining))
    return r


@functools.singledispatch
def largest_gap(target, in_extended=None):
    raise NotImplementedError(target)


@largest_gap.register(Disk)
@largest_gap.register(Raid)
@largest_gap.register(LVM_VolGroup)
def _largest_gap_disk(device, in_extended=None):
    largest_size = 0
    largest = None
    for pg in parts_and_gaps(device):
        if isinstance(pg, Gap):
            if in_extended is not None and pg.in_extended != in_extended:
                continue
            if pg.size > largest_size:
                largest = pg
                largest_size = pg.size
    return largest


@largest_gap.register(list)
def _largest_gap_list(disks, in_extended=None):
    largest = None
    for gap in (largest_gap(d, in_extended) for d in disks):
        if largest is None or (gap is not None and gap.size > largest.size):
            largest = gap
    return largest


def largest_gap_size(device, in_extended=None):
    largest = largest_gap(device, in_extended)
    if largest is not None:
        return largest.size
    return 0


@functools.singledispatch
def movable_trailing_partitions_and_gap_size(partition):
    """For a given partition (or LVM logical volume), return the total,
    potentially available, free space immediately following the partition.
    By potentially available, we mean that to claim that much free space, some
    other partitions might need to be moved.
    The return value is a tuple that has two values:
     * the list of partitions that would need to be moved
     * the total potentially available free space
    """
    raise NotImplementedError


@movable_trailing_partitions_and_gap_size.register
def _movable_trailing_partitions_and_gap_size_partition(
    partition: Partition,
) -> Tuple[List[Partition], int]:
    pgs = parts_and_gaps(partition.device)
    part_idx = pgs.index(partition)
    trailing_partitions = []
    in_extended = partition.is_logical
    for pg in pgs[part_idx + 1 :]:
        if isinstance(pg, Partition):
            if pg.preserve:
                break
            if in_extended and not pg.is_logical:
                break
            trailing_partitions.append(pg)
        else:
            if pg.in_extended == in_extended:
                return (trailing_partitions, pg.size)
            else:
                return (trailing_partitions, 0)
    return (trailing_partitions, 0)


@movable_trailing_partitions_and_gap_size.register
def _movable_trailing_partitions_and_gap_size_lvm(
    volume: LVM_LogicalVolume,
) -> Tuple[List[LVM_LogicalVolume], int]:
    # In a Volume Group, there is no need to move partitions around, one can
    # always use the remaining space.

    return ([], largest_gap_size(volume.volgroup))


def at_offset(device, offset):
    for pg in parts_and_gaps(device):
        if isinstance(pg, Gap):
            if pg.offset == offset:
                return pg
    return None


def after(device, offset):
    """Find the first gap that is after this offset."""
    for pg in parts_and_gaps(device):
        if isinstance(pg, Gap):
            if pg.offset > offset:
                return pg
    return None
