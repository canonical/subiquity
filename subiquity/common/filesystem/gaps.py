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
    Disk,
    LVM_CHUNK_SIZE,
    LVM_VolGroup,
    Partition,
    Raid,
    )


# should also set on_setattr=None with attrs 20.1.0
@attr.s(auto_attribs=True, frozen=True)
class Gap:
    device: object
    offset: int
    size: int
    in_extended: bool = False

    type: str = 'gap'

    @property
    def id(self):
        return 'gap-' + self.device.id

    def split(self, size):
        """returns a tuple of two new gaps, split from the current gap based on
        the supplied size.  If size is equal to the gap size, the second gap is
        None.  The original gap is unmodified."""
        if size > self.size:
            raise Exception('requested size larger than gap')
        if size == self.size:
            return (self, None)
        first_gap = Gap(device=self.device,
                        offset=self.offset,
                        size=size,
                        in_extended=self.in_extended)
        rest_gap = Gap(device=self.device,
                       offset=self.offset + size,
                       size=self.size - size,
                       in_extended=self.in_extended)
        return (first_gap, rest_gap)


@functools.singledispatch
def parts_and_gaps(device):
    raise NotImplementedError(device)


def find_disk_gaps_v1(device):
    r = []
    used = 0
    ad = device.alignment_data()
    used += ad.min_start_offset
    for p in device._partitions:
        used = align_up(used + p.size, 1 << 20)
        r.append(p)
    if device._has_preexisting_partition():
        return r
    if device.ptable == 'vtoc' and len(device._partitions) >= 3:
        return r
    end = align_down(device.size - ad.min_end_offset, 1 << 20)
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
        if end - start >= info.min_gap_size:
            result.append(Gap(device, start, end - start, in_extended))

    prev_end = info.min_start_offset

    parts = sorted(device._partitions, key=lambda p: p.offset)
    extended_end = None

    for part in parts + [None]:
        if part is None:
            gap_end = ad(device.size - info.min_end_offset)
        else:
            gap_end = ad(part.offset)

        gap_start = au(prev_end)

        if extended_end is not None:
            gap_start = min(
                extended_end, au(gap_start + info.ebr_space))

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


def movable_trailing_partitions_and_gap_size(partition):
    pgs = parts_and_gaps(partition.device)
    part_idx = pgs.index(partition)
    trailing_partitions = []
    in_extended = partition.flag == "logical"
    for pg in pgs[part_idx + 1:]:
        if isinstance(pg, Partition):
            if pg.preserve:
                break
            if in_extended and pg.flag != "logical":
                break
            trailing_partitions.append(pg)
        else:
            if pg.in_extended == in_extended:
                return (trailing_partitions, pg.size)
            else:
                return (trailing_partitions, 0)
    return (trailing_partitions, 0)


def at_offset(device, offset):
    for pg in parts_and_gaps(device):
        if isinstance(pg, Gap):
            if pg.offset == offset:
                return pg
    return None
