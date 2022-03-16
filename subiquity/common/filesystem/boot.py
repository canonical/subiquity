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

from subiquity.common.filesystem import gaps, sizes
from subiquity.models.filesystem import (
    Disk,
    Raid,
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


@is_boot_device.register(Raid)
def _is_boot_device_raid(raid):
    bl = raid._m.bootloader
    if bl != Bootloader.UEFI:
        return False
    if not raid.container or raid.container.metadata != 'imsm':
        return False
    return any(p.grub_device for p in raid._partitions)


@attr.s(auto_attribs=True)
class CreatePartPlan:
    device: object

    offset: int = 0

    spec: dict = attr.ib(factory=dict)
    args: dict = attr.ib(factory=dict)

    def apply(self, manipulator):
        manipulator.create_partition(
            self.device, gaps.Gap(self.device, self.offset, 0), self.spec,
            **self.args)


@attr.s(auto_attribs=True)
class ResizePlan:
    part: object
    size_delta: int = 0

    def apply(self, manipulator):
        self.part.size += self.size_delta


@attr.s(auto_attribs=True)
class SlidePlan:
    parts: list
    offset_delta: int = 0

    def apply(self, manipulator):
        for part in self.parts:
            part.offset += self.offset_delta


@attr.s(auto_attribs=True)
class SetAttrPlan:
    device: object
    attr: str
    val: str

    def apply(self, manipulator):
        setattr(self.device, self.attr, self.val)


@attr.s(auto_attribs=True)
class MountBootEfiPlan:
    part: object

    def apply(self, manipulator):
        manipulator._mount_esp(self.part)


@attr.s(auto_attribs=True)
class MultiStepPlan:
    plans: list

    def apply(self, manipulator):
        for plan in self.plans:
            plan.apply(manipulator)


def get_boot_device_plan_bios(device):
    attr_plan = SetAttrPlan(device, 'grub_device', True)
    if device.ptable == 'msdos':
        return attr_plan
    if device._has_preexisting_partition():
        if device._partitions[0].flag == "bios_grub":
            return attr_plan
        else:
            return None

    create_part_plan = CreatePartPlan(
        device=device,
        offset=sizes.BIOS_GRUB_SIZE_BYTES,
        spec=dict(size=sizes.BIOS_GRUB_SIZE_BYTES, fstype=None, mount=None),
        args=dict(flag='bios_grub'))

    partitions = device.partitions()

    if gaps.largest_gap_size(device) >= sizes.BIOS_GRUB_SIZE_BYTES:
        return MultiStepPlan(plans=[
            SlidePlan(
                parts=partitions,
                offset_delta=sizes.BIOS_GRUB_SIZE_BYTES),
            create_part_plan,
            attr_plan,
            ])
    else:
        largest_i, largest_part = max(
            enumerate(partitions),
            key=lambda i_p: i_p[1].size)
        return MultiStepPlan(plans=[
            SlidePlan(
                parts=partitions[:largest_i+1],
                offset_delta=sizes.BIOS_GRUB_SIZE_BYTES),
            ResizePlan(
                part=largest_part,
                size_delta=-sizes.BIOS_GRUB_SIZE_BYTES),
            create_part_plan,
            attr_plan,
            ])


def get_boot_device_plan_uefi(device):
    if device._has_preexisting_partition():
        for part in device.partitions():
            if is_esp(part):
                plans = [SetAttrPlan(part, 'grub_device', True)]
                if device._m._mount_for_path('/boot/efi') is None:
                    plans.append(MountBootEfiPlan(part))
                return MultiStepPlan(plans=plans)
        return None

    size = sizes.get_efi_size(device)

    create_part_plan = CreatePartPlan(
        device=device,
        offset=None,
        spec=dict(size=size, fstype='fat32', mount=None),
        args=dict(flag='boot', grub_device=True))
    if device._m._mount_for_path("/boot/efi") is None:
        create_part_plan.spec['mount'] = '/boot/efi'

    partitions = device.partitions()

    if gaps.largest_gap_size(device) >= size:
        create_part_plan.offset = gaps.largest_gap(device).offset
        return create_part_plan
    else:
        largest_i, largest_part = max(
            enumerate(partitions),
            key=lambda i_p: i_p[1].size)
        create_part_plan.offset = largest_part.offset
        return MultiStepPlan(plans=[
            SlidePlan(
                parts=[largest_part],
                offset_delta=size),
            ResizePlan(
                part=largest_part,
                size_delta=-size),
            create_part_plan,
            ])


def get_boot_device_plan(device):
    bl = device._m.bootloader
    if bl == Bootloader.BIOS:
        return get_boot_device_plan_bios(device)
    if bl == Bootloader.UEFI:
        return get_boot_device_plan_uefi(device)
    raise Exception(f'unexpected bootloader {bl} here')


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
    if with_reformatting:
        return True
    if bl in [Bootloader.BIOS, Bootloader.UEFI]:
        return get_boot_device_plan(disk) is not None
    if disk._has_preexisting_partition():
        if bl == Bootloader.PREP:
            return any(p.flag == "prep" for p in disk._partitions)
        else:
            raise Exception(f'unexpected bootloader {bl} here')
    else:
        return True


@can_be_boot_device.register(Raid)
def _can_be_boot_device_raid(raid, *, with_reformatting=False):
    bl = raid._m.bootloader
    if bl != Bootloader.UEFI:
        return False
    if not raid.container or raid.container.metadata != 'imsm':
        return False
    if with_reformatting:
        return True
    return get_boot_device_plan_uefi(raid) is not None


@functools.singledispatch
def is_esp(device):
    """Is `device` a UEFI ESP?"""
    return False


@is_esp.register(Partition)
def _is_esp_partition(partition):
    if not can_be_boot_device(partition.device, with_reformatting=True):
        return False
    if partition.device.ptable == "gpt":
        return partition.flag == "boot"
    elif isinstance(partition.device, Disk):
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
    else:
        return False


def all_boot_devices(model):
    """Return all current boot devices for `model`."""
    candidates = model.all_disks() + model.all_raids()
    return [cand for cand in candidates if is_boot_device(cand)]


def is_bootloader_partition(partition):
    if partition._m.bootloader == Bootloader.BIOS:
        return partition.flag == "bios_grub"
    elif partition._m.bootloader == Bootloader.UEFI:
        return is_esp(partition)
    elif partition._m.bootloader == Bootloader.PREP:
        return partition.flag == "prep"
    else:
        return False
