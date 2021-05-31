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
    LVM_LogicalVolume,
    LVM_VolGroup,
    Partition,
    Raid,
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


@functools.singledispatch
def desc(device):
    raise NotImplementedError(repr(device))


@desc.register(Disk)
def _desc_disk(disk):
    if disk.multipath:
        return _("multipath device")
    return _("local disk")


@desc.register(Partition)
def _desc_partition(partition):
    return _("partition of {device}").format(device=desc(partition.device))


@desc.register(Raid)
def _desc_raid(raid):
    return _("software RAID {level}").format(level=raid.raidlevel[4:])


@desc.register(LVM_VolGroup)
def _desc_vg(vg):
    return _("LVM volume group")


@desc.register(LVM_LogicalVolume)
def _desc_lv(lv):
    return _("LVM logival volume")


@functools.singledispatch
def label(device, *, short=False):
    raise NotImplementedError(repr(device))


@label.register(Disk)
def _label_disk(disk, *, short=False):
    if disk.multipath and disk.wwn:
        return disk.wwn
    if disk.serial:
        return disk.serial
    return disk.path


@label.register(Raid)
@label.register(LVM_VolGroup)
@label.register(LVM_LogicalVolume)
def _label_just_name(device, *, short=False):
    return device.name


@label.register(Partition)
def _label_partition(partition, *, short=False):
    if short:
        return _("partition {number}").format(number=partition._number)
    else:
        return _("partition {number} of {device}").format(
            number=partition._number, device=label(partition.device))


def _usage_labels_generic(device):
    cd = device.constructed_device()
    if cd is not None:
        return [
            _("{component_name} of {desc} {name}").format(
                component_name=cd.component_name,
                desc=desc(cd),
                name=cd.name),
            ]
    fs = device.fs()
    if fs is not None:
        if fs.preserve:
            format_desc = _("already formatted as {fstype}")
        elif device.original_fstype() is not None:
            format_desc = _("to be reformatted as {fstype}")
        else:
            format_desc = _("to be formatted as {fstype}")
        r = [format_desc.format(fstype=fs.fstype)]
        if device._m.is_mounted_filesystem(fs.fstype):
            m = fs.mount()
            if m:
                # A filesytem
                r.append(_("mounted at {path}").format(path=m.path))
            elif not getattr(device, 'is_esp', False):
                # A filesytem
                r.append(_("not mounted"))
        elif fs.preserve:
            if fs.mount() is None:
                # A filesytem that cannot be mounted (i.e. swap)
                # is used or unused
                r.append(_("unused"))
            else:
                # A filesytem that cannot be mounted (i.e. swap)
                # is used or unused
                r.append(_("used"))
        return r
    else:
        return [_("unused")]


@functools.singledispatch
def usage_labels(device):
    return _usage_labels_generic(device)


@usage_labels.register(Partition)
def _usage_labels_partition(partition):
    if partition.flag == "prep" or partition.flag == "bios_grub":
        return []
    return _usage_labels_generic(partition)
