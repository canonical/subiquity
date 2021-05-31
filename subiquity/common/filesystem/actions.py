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

from subiquitycore.gettext38 import pgettext

from subiquity.models.filesystem import (
    Bootloader,
    Disk,
    LVM_LogicalVolume,
    LVM_VolGroup,
    Partition,
    Raid,
    )


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


@functools.singledispatch
def supported_actions(device):
    raise NotImplementedError(
        "supported_actions({}) not defined".format(device))


@supported_actions.register(Disk)
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


@supported_actions.register(Partition)
def _part_actions(part):
    return [
        DeviceAction.EDIT,
        DeviceAction.REMOVE,
        DeviceAction.DELETE,
        ]


@supported_actions.register(Raid)
def _raid_actions(raid):
    return [
        DeviceAction.EDIT,
        DeviceAction.PARTITION,
        DeviceAction.FORMAT,
        DeviceAction.REMOVE,
        DeviceAction.DELETE,
        DeviceAction.REFORMAT,
        ]


@supported_actions.register(LVM_VolGroup)
def _vg_actions(vg):
    return [
        DeviceAction.EDIT,
        DeviceAction.CREATE_LV,
        DeviceAction.DELETE,
        ]


@supported_actions.register(LVM_LogicalVolume)
def _lv_actions(lv):
    return [
        DeviceAction.EDIT,
        DeviceAction.DELETE,
        ]
