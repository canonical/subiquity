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


@functools.singledispatch
def is_esp(device):
    """Is `device` a UEFI ESP?"""
    return False


@is_esp.register(Partition)
def _is_esp_partition(partition):
    if partition.device.type != "disk":
        return False
    if partition.device.ptable == "gpt":
        return partition.flag == "boot"
    else:
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


def all_boot_devices(model):
    """Return all current boot devices for `model`."""
    return [disk for disk in model.all_disks() if is_boot_device(disk)]


def is_bootloader_partition(partition):
    if partition._m.bootloader == Bootloader.BIOS:
        return partition.flag == "bios_grub"
    elif partition._m.bootloader == Bootloader.UEFI:
        return is_esp(partition)
    elif partition._m.bootloader == Bootloader.PREP:
        return partition.flag == "prep"
    else:
        return False
