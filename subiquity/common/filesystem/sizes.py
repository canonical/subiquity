# Copyright 2022 Canonical, Ltd.
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

from subiquity.models.filesystem import (
    MiB,
    )


BIOS_GRUB_SIZE_BYTES = 1 * MiB
PREP_GRUB_SIZE_BYTES = 8 * MiB


@attr.s(auto_attribs=True)
class PartitionScaleFactors:
    minimum: int
    priority: int
    maximum: int


uefi_scale = PartitionScaleFactors(
        minimum=538 * MiB,
        priority=538,
        maximum=1075 * MiB)
bootfs_scale = PartitionScaleFactors(
        minimum=768 * MiB,
        priority=1024,
        maximum=1536 * MiB)
rootfs_scale = PartitionScaleFactors(
        minimum=900 * MiB,
        priority=10000,
        maximum=-1)


def scale_partitions(all_factors, disk_size):
    """for the list of scale factors, provide list of scaled partition size.
    Assumes at most one scale factor with maximum==-1, and
    disk_size is at least as big as the sum of all partition minimums.
    The scale factor with maximum==-1 is given all remaining disk space."""
    ret = []
    sum_priorities = sum([factor.priority for factor in all_factors])
    for cur in all_factors:
        scaled = int((disk_size / sum_priorities) * cur.priority)
        if scaled < cur.minimum:
            ret.append(cur.minimum)
        elif scaled > cur.maximum:
            ret.append(cur.maximum)
        else:
            ret.append(scaled)
    if -1 in ret:
        used = sum(filter(lambda x: x != -1, ret))
        idx = ret.index(-1)
        ret[idx] = disk_size - used
    return ret


def get_efi_size(disk):
    all_factors = (uefi_scale, bootfs_scale, rootfs_scale)
    return scale_partitions(all_factors, disk.size)[0]


def get_bootfs_size(disk):
    all_factors = (uefi_scale, bootfs_scale, rootfs_scale)
    return scale_partitions(all_factors, disk.size)[1]
