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

import enum
import functools
from gettext import pgettext

from subiquity.common.filesystem import boot, labels
from subiquity.models.filesystem import (
    Bootloader,
    Disk,
    LVM_LogicalVolume,
    LVM_VolGroup,
    Partition,
    Raid,
    raidlevels_by_value,
    )


_checkers = {}


def make_checker(action):
    @functools.singledispatch
    def impl(device):
        raise NotImplementedError(
            "checker for %s on %s not implemented" % (
                action, device))
    _checkers[action] = impl
    return impl


class DeviceAction(enum.Enum):
    # Information about a drive
    INFO = pgettext("DeviceAction", "Info")
    # Edit a device (partition, logical volume, RAID, etc)
    EDIT = pgettext("DeviceAction", "Edit")
    REFORMAT = pgettext("DeviceAction", "Reformat")
    PARTITION = pgettext("DeviceAction", "Add Partition")
    CREATE_LV = pgettext("DeviceAction", "Create Logical Volume")
    FORMAT = pgettext("DeviceAction", "Format")
    REMOVE = pgettext("DeviceAction", "Remove from RAID/LVM")
    DELETE = pgettext("DeviceAction", "Delete")
    TOGGLE_BOOT = pgettext("DeviceAction", "Make Boot Device")

    def str(self):
        return pgettext(type(self).__name__, self.value)

    @classmethod
    def supported(self, device):
        return _supported_actions(device)

    def can(self, device):
        assert self in self.supported(device)
        r = _checkers[self](device)
        if isinstance(r, bool):
            return r, None
        elif isinstance(r, str):
            return False, r
        else:
            return r


@functools.singledispatch
def _supported_actions(device):
    raise NotImplementedError(
        "_supported_actions({}) not defined".format(device))


@_supported_actions.register(Disk)
def _disk_actions(disk):
    actions = [
        DeviceAction.INFO,
        DeviceAction.REFORMAT,
        DeviceAction.PARTITION,
        DeviceAction.FORMAT,
        DeviceAction.REMOVE,
        ]
    if disk._m.bootloader != Bootloader.NONE:
        actions.append(DeviceAction.TOGGLE_BOOT)
    return actions


@_supported_actions.register(Partition)
def _part_actions(part):
    return [
        DeviceAction.EDIT,
        DeviceAction.REMOVE,
        DeviceAction.DELETE,
        ]


@_supported_actions.register(Raid)
def _raid_actions(raid):
    if raid.raidlevel == "container":
        return [
            DeviceAction.EDIT,
            DeviceAction.DELETE,
            ]
    else:
        actions = [
            DeviceAction.EDIT,
            DeviceAction.PARTITION,
            DeviceAction.FORMAT,
            DeviceAction.REMOVE,
            DeviceAction.DELETE,
            DeviceAction.REFORMAT,
            ]
        if raid._m.bootloader == Bootloader.UEFI:
            if raid.container and raid.container.metadata == 'imsm':
                actions.append(DeviceAction.TOGGLE_BOOT)
        return actions


@_supported_actions.register(LVM_VolGroup)
def _vg_actions(vg):
    return [
        DeviceAction.EDIT,
        DeviceAction.CREATE_LV,
        DeviceAction.DELETE,
        ]


@_supported_actions.register(LVM_LogicalVolume)
def _lv_actions(lv):
    return [
        DeviceAction.EDIT,
        DeviceAction.DELETE,
        ]


_can_info = make_checker(DeviceAction.INFO)


@_can_info.register(Disk)
def _disk_info(disk):
    return True


_can_edit = make_checker(DeviceAction.EDIT)


def _can_edit_generic(device):
    cd = device.constructed_device()
    if cd is None:
        return True
    return _(
        "Cannot edit {selflabel} as it is part of the {cdtype} "
        "{cdname}.").format(
            selflabel=labels.label(device),
            cdtype=labels.desc(cd),
            cdname=labels.label(cd))


_can_edit.register(Partition, _can_edit_generic)
_can_edit.register(LVM_LogicalVolume, _can_edit_generic)


@_can_edit.register(Raid)
def _can_edit_raid(raid):
    if raid.preserve:
        return _("Cannot edit pre-existing RAIDs.")
    elif len(raid._partitions) > 0:
        return _(
            "Cannot edit {raidlabel} because it has partitions.").format(
                raidlabel=labels.label(raid))
    else:
        return _can_edit_generic(raid)


@_can_edit.register(LVM_VolGroup)
def _can_edit_vg(vg):
    if vg.preserve:
        return _("Cannot edit pre-existing volume groups.")
    elif len(vg._partitions) > 0:
        return _(
            "Cannot edit {vglabel} because it has logical "
            "volumes.").format(
                vglabel=labels.label(vg))
    else:
        return _can_edit_generic(vg)


_can_reformat = make_checker(DeviceAction.REFORMAT)


@_can_reformat.register(Disk)
@_can_reformat.register(Raid)
def _can_reformat_device(device):
    if len(device._partitions) == 0:
        return False
    for p in device._partitions:
        if p._constructed_device is not None:
            return False
    return True


_can_partition = make_checker(DeviceAction.PARTITION)


@_can_partition.register(Disk)
@_can_partition.register(Raid)
def _can_partition_device(device):
    if device._has_preexisting_partition():
        return False
    if device.free_for_partitions <= 0:
        return False
    # We only create msdos partition tables with FBA dasds, which
    # only support 3 partitions. As and when we support editing
    # partition msdos tables we'll need to be more clever here.
    if device.ptable in ['vtoc', 'msdos'] and len(device._partitions) >= 3:
        return False
    return True


_can_create_lv = make_checker(DeviceAction.CREATE_LV)


@_can_create_lv.register(LVM_VolGroup)
def _can_create_lv_vg(vg):
    return not vg.preserve and vg.free_for_partitions > 0


_can_format = make_checker(DeviceAction.FORMAT)


@_can_format.register(Disk)
@_can_format.register(Raid)
def _can_format_device(device):
    return len(device._partitions) == 0 and device._constructed_device is None


_can_remove = make_checker(DeviceAction.REMOVE)


@_can_remove.register(Disk)
@_can_remove.register(Partition)
@_can_remove.register(Raid)
def _can_remove_device(device):
    cd = device.constructed_device()
    if cd is None:
        return False
    if cd.preserve:
        return _("Cannot remove {selflabel} from pre-existing {cdtype} "
                 "{cdlabel}.").format(
                    selflabel=labels.label(device),
                    cdtype=labels.desc(cd),
                    cdlabel=labels.label(cd))
    if isinstance(cd, Raid):
        if device in cd.spare_devices:
            return True
        min_devices = raidlevels_by_value[cd.raidlevel].min_devices
        if len(cd.devices) == min_devices:
            return _(
                "Removing {selflabel} would leave the {cdtype} {cdlabel} with "
                "less than {min_devices} devices.").format(
                    selflabel=labels.label(device),
                    cdtype=labels.desc(cd),
                    cdlabel=labels.label(cd),
                    min_devices=min_devices)
    elif isinstance(cd, LVM_VolGroup):
        if len(cd.devices) == 1:
            return _(
                "Removing {selflabel} would leave the {cdtype} {cdlabel} with "
                "no devices.").format(
                    selflabel=labels.label(device),
                    cdtype=labels.desc(cd),
                    cdlabel=labels.label(cd))
    return True


_can_delete = make_checker(DeviceAction.DELETE)


def _can_delete_generic(device):
    cd = device.constructed_device()
    if cd is None:
        return True
    return _(
        "Cannot delete {selflabel} as it is part of the {cdtype} "
        "{cdname}.").format(
            selflabel=labels.label(device),
            cdtype=labels.desc(cd),
            cdname=labels.label(cd))


@_can_delete.register(Partition)
def _can_delete_partition(partition):
    if partition.device._has_preexisting_partition():
        return _("Cannot delete a single partition from a device that "
                 "already has partitions.")
    if boot.is_bootloader_partition(partition):
        return _("Cannot delete required bootloader partition")
    return _can_delete_generic(partition)


@_can_delete.register(Raid)
@_can_delete.register(LVM_VolGroup)
def _can_delete_raid_vg(device):
    mounted_partitions = 0
    for p in device._partitions:
        if p.fs() and p.fs().mount():
            mounted_partitions += 1
        elif p.constructed_device():
            cd = p.constructed_device()
            return _(
                "Cannot delete {devicelabel} as partition {partnum} is part "
                "of the {cdtype} {cdname}.").format(
                    devicelabel=labels.label(device),
                    partnum=p._number,
                    cdtype=labels.desc(cd),
                    cdname=labels.label(cd),
                    )
    if mounted_partitions > 1:
        return _(
            "Cannot delete {devicelabel} because it has {count} mounted "
            "partitions.").format(
                devicelabel=labels.label(device),
                count=mounted_partitions)
    elif mounted_partitions == 1:
        return _(
            "Cannot delete {devicelabel} because it has 1 mounted partition."
            ).format(devicelabel=labels.label(device))
    else:
        return _can_delete_generic(device)


@_can_delete.register(LVM_LogicalVolume)
def _can_delete_lv(lv):
    if lv.volgroup._has_preexisting_partition():
        return _("Cannot delete a single logical volume from a volume "
                 "group that already has logical volumes.")
    return True


_can_toggle_boot = make_checker(DeviceAction.TOGGLE_BOOT)


@_can_toggle_boot.register(Disk)
@_can_toggle_boot.register(Raid)
def _can_toggle_boot_disk(disk):
    if boot.is_boot_device(disk):
        for disk2 in boot.all_boot_devices(disk._m):
            if disk2 is not disk:
                return True
        return False
    elif disk._fs is not None or disk._constructed_device is not None:
        return False
    else:
        return boot.can_be_boot_device(disk)
