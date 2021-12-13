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
    GPT_OVERHEAD,
    Raid,
    )


@attr.s(auto_attribs=True)
class Gap:
    device: object
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
    for p in device._partitions:
        used = align_up(used + p.size, 1 << 20)
        r.append(p)
    if device._has_preexisting_partition():
        return r
    if device.ptable == 'vtoc' and len(device._partitions) >= 3:
        return r
    end = align_down(device.size, 1 << 20) - GPT_OVERHEAD
    if end - used >= (1 << 20):
        r.append(Gap(device, end - used))
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
        r.append(Gap(device, remaining))
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
