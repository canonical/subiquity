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

from subiquity.models.filesystem import (
    Disk,
    LVM_VolGroup,
    Partition,
    )


def _annotations_generic(device):
    preserve = getattr(device, 'preserve', None)
    if preserve is None:
        return []
    elif preserve:
        # A pre-existing device such as a partition or RAID
        return [_("existing")]
    else:
        # A newly created device such as a partition or RAID
        return [_("new")]


@functools.singledispatch
def annotations(device):
    return _annotations_generic(device)


@annotations.register(Disk)
def _annotations_disk(disk):
    return []


@annotations.register(Partition)
def _annotations_partition(partition):
    r = _annotations_generic(partition)
    if partition.flag == "prep":
        r.append("PReP")
        if partition.preserve:
            if partition.grub_device:
                # boot loader partition
                r.append(_("configured"))
            else:
                # boot loader partition
                r.append(_("unconfigured"))
    elif partition.is_esp:
        if partition.fs() and partition.fs().mount():
            r.append(_("primary ESP"))
        elif partition.grub_device:
            r.append(_("backup ESP"))
        else:
            r.append(_("unused ESP"))
    elif partition.flag == "bios_grub":
        if partition.preserve:
            if partition.device.grub_device:
                r.append(_("configured"))
            else:
                r.append(_("unconfigured"))
        r.append("bios_grub")
    elif partition.flag == "extended":
        # extended partition
        r.append(_("extended"))
    elif partition.flag == "logical":
        # logical partition
        r.append(_("logical"))
    return r


@annotations.register(LVM_VolGroup)
def _annotations_vg(vg):
    r = _annotations_generic(vg)
    member = next(iter(vg.devices))
    if member.type == "dm_crypt":
        # Flag for a LVM volume group
        r.append(_("encrypted"))
    return r
