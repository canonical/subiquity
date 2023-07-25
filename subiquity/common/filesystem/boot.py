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

import abc
import functools
import logging
from typing import Any, Optional

import attr

from subiquity.common.filesystem import gaps, sizes
from subiquity.models.filesystem import Bootloader, Disk, Partition, Raid, align_up

log = logging.getLogger("subiquity.common.filesystem.boot")


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
    if not raid.container or raid.container.metadata != "imsm":
        return False
    return any(p.grub_device for p in raid._partitions)


class MakeBootDevicePlan(abc.ABC):
    """A way of making a device into boot device.

    The code for checking if a device can be a boot device attempts to
    construct one of these to find out. The code for making a device a
    boot device calls apply(). This way we don't have to keep the
    implementation of "can this be a boot device" and "how do we make
    this a boot device" in sync.
    """

    @abc.abstractmethod
    def apply(self, manipulator):
        pass


@attr.s(auto_attribs=True)
class CreatePartPlan(MakeBootDevicePlan):
    """Create a partition on the device."""

    gap: gaps.Gap

    spec: dict = attr.ib(factory=dict)
    args: dict = attr.ib(factory=dict)

    def apply(self, manipulator):
        manipulator.create_partition(self.gap.device, self.gap, self.spec, **self.args)


def _can_resize_part(inst, field, part):
    assert not part.preserve or inst.allow_resize_preserved


@attr.s(auto_attribs=True)
class ResizePlan(MakeBootDevicePlan):
    """Resize a partition."""

    part: object = attr.ib(validator=_can_resize_part)
    size_delta: int = 0
    allow_resize_preserved: bool = False

    def apply(self, manipulator):
        self.part.size += self.size_delta
        if self.part.preserve:
            self.part.resize = True


def _no_preserve_parts(inst, field, parts):
    for part in parts:
        assert not part.preserve


@attr.s(auto_attribs=True)
class SlidePlan(MakeBootDevicePlan):
    """Move a collection of partitions by the same amount."""

    parts: list = attr.ib(validator=_no_preserve_parts)
    offset_delta: int = 0

    def apply(self, manipulator):
        for part in self.parts:
            part.offset += self.offset_delta


@attr.s(auto_attribs=True)
class SetAttrPlan(MakeBootDevicePlan):
    """Set an attribute on an object."""

    device: object
    attr: str
    val: Any

    def apply(self, manipulator):
        setattr(self.device, self.attr, self.val)


@attr.s(auto_attribs=True)
class MountBootEfiPlan(MakeBootDevicePlan):
    """Mount a partition at /boot/efi."""

    part: object

    def apply(self, manipulator):
        manipulator._mount_esp(self.part)


@attr.s(auto_attribs=True)
class NoOpBootPlan(MakeBootDevicePlan):
    """Do nothing, successfully"""

    def apply(self, manipulator):
        pass


@attr.s(auto_attribs=True)
class MultiStepPlan(MakeBootDevicePlan):
    """Execute several MakeBootDevicePlans in sequence."""

    plans: list

    def apply(self, manipulator):
        for plan in self.plans:
            plan.apply(manipulator)


def get_boot_device_plan_bios(device) -> Optional[MakeBootDevicePlan]:
    attr_plan = SetAttrPlan(device, "grub_device", True)
    if device.ptable == "msdos":
        return attr_plan
    pgs = gaps.parts_and_gaps(device)
    if len(pgs) > 0:
        if isinstance(pgs[0], Partition) and pgs[0].flag == "bios_grub":
            return attr_plan

    gap = gaps.Gap(
        device=device,
        offset=device.alignment_data().min_start_offset,
        size=sizes.BIOS_GRUB_SIZE_BYTES,
    )
    create_part_plan = CreatePartPlan(
        gap=gap,
        spec=dict(size=sizes.BIOS_GRUB_SIZE_BYTES, fstype=None, mount=None),
        args=dict(flag="bios_grub"),
    )

    movable = []

    for pg in pgs:
        if isinstance(pg, gaps.Gap):
            if pg.size >= sizes.BIOS_GRUB_SIZE_BYTES:
                return MultiStepPlan(
                    plans=[
                        SlidePlan(
                            parts=movable, offset_delta=sizes.BIOS_GRUB_SIZE_BYTES
                        ),
                        create_part_plan,
                        attr_plan,
                    ]
                )
            else:
                return None
        elif pg.preserve:
            break
        else:
            movable.append(pg)

    if not movable:
        return None

    largest_i, largest_part = max(enumerate(movable), key=lambda i_p: i_p[1].size)
    return MultiStepPlan(
        plans=[
            ResizePlan(part=largest_part, size_delta=-sizes.BIOS_GRUB_SIZE_BYTES),
            SlidePlan(
                parts=movable[: largest_i + 1], offset_delta=sizes.BIOS_GRUB_SIZE_BYTES
            ),
            create_part_plan,
            attr_plan,
        ]
    )


def get_add_part_plan(device, *, spec, args, resize_partition=None):
    size = spec["size"]
    partitions = device.partitions()

    create_part_plan = CreatePartPlan(gap=None, spec=spec, args=args)

    # Per LP: #1796260, it is known that putting an ESP on a logical partition
    # is a bad idea.  So avoid putting any sort of boot stuff on a logical -
    # it's probably a bad idea for all cases.

    gap = gaps.largest_gap(device, in_extended=False)
    if gap is not None and gap.size >= size and gap.is_usable:
        create_part_plan.gap = gap.split(size)[0]
        return create_part_plan
    elif resize_partition is not None and not resize_partition.is_logical:
        if size > resize_partition.size - resize_partition.estimated_min_size:
            return None

        offset = resize_partition.offset + resize_partition.size - size
        create_part_plan.gap = gaps.Gap(device=device, offset=offset, size=size)
        return MultiStepPlan(
            plans=[
                ResizePlan(
                    part=resize_partition,
                    size_delta=-size,
                    allow_resize_preserved=True,
                ),
                create_part_plan,
            ]
        )
    else:
        new_primaries = [
            p
            for p in partitions
            if not p.preserve
            if p.flag not in ("extended", "logical")
        ]
        if not new_primaries:
            return None
        largest_part = max(new_primaries, key=lambda p: p.size)
        if size > largest_part.size // 2:
            return None
        create_part_plan.gap = gaps.Gap(
            device=device, offset=largest_part.offset, size=size
        )
        return MultiStepPlan(
            plans=[
                ResizePlan(part=largest_part, size_delta=-size),
                SlidePlan(parts=[largest_part], offset_delta=size),
                create_part_plan,
            ]
        )


def get_boot_device_plan_uefi(device, resize_partition):
    for part in device.partitions():
        if is_esp(part):
            plans = [SetAttrPlan(part, "grub_device", True)]
            if device._m._mount_for_path("/boot/efi") is None:
                plans.append(MountBootEfiPlan(part))
            return MultiStepPlan(plans=plans)

    part_align = device.alignment_data().part_align
    size = align_up(sizes.get_efi_size(device.size), part_align)
    spec = dict(size=size, fstype="fat32", mount=None)
    if device._m._mount_for_path("/boot/efi") is None:
        spec["mount"] = "/boot/efi"

    return get_add_part_plan(
        device,
        spec=spec,
        args=dict(flag="boot", grub_device=True),
        resize_partition=resize_partition,
    )


def get_boot_device_plan_prep(device, resize_partition):
    for part in device.partitions():
        if part.flag == "prep":
            return MultiStepPlan(
                plans=[
                    SetAttrPlan(part, "grub_device", True),
                    SetAttrPlan(part, "wipe", "zero"),
                ]
            )

    return get_add_part_plan(
        device,
        spec=dict(size=sizes.PREP_GRUB_SIZE_BYTES, fstype=None, mount=None),
        args=dict(flag="prep", grub_device=True, wipe="zero"),
        resize_partition=resize_partition,
    )


def get_boot_device_plan(device, resize_partition=None):
    bl = device._m.bootloader
    if bl == Bootloader.BIOS:
        # we don't attempt resize_partition with BIOS,
        # a move might help but a resize alone won't
        # and we don't move preserved partitions.
        return get_boot_device_plan_bios(device)
    if bl == Bootloader.UEFI:
        return get_boot_device_plan_uefi(device, resize_partition)
    if bl == Bootloader.PREP:
        return get_boot_device_plan_prep(device, resize_partition)
    if bl == Bootloader.NONE:
        return NoOpBootPlan()
    raise Exception(f"unexpected bootloader {bl} here")


@functools.singledispatch
def can_be_boot_device(device, *, resize_partition=None, with_reformatting=False):
    """Can `device` be made into a boot device?

    If with_reformatting=True, return true if the device can be made
    into a boot device after reformatting.
    """
    return False


@can_be_boot_device.register(Disk)
def _can_be_boot_device_disk(disk, *, resize_partition=None, with_reformatting=False):
    if with_reformatting:
        disk = disk._reformatted()
    plan = get_boot_device_plan(disk, resize_partition=resize_partition)
    return plan is not None


@can_be_boot_device.register(Raid)
def _can_be_boot_device_raid(raid, *, resize_partition=None, with_reformatting=False):
    bl = raid._m.bootloader
    if bl != Bootloader.UEFI:
        return False
    if not raid.container or raid.container.metadata != "imsm":
        return False
    if with_reformatting:
        return True
    plan = get_boot_device_plan_uefi(raid, resize_partition=resize_partition)
    return plan is not None


@functools.singledispatch
def is_esp(device):
    """Is `device` a UEFI ESP?"""
    return False


@is_esp.register(Partition)
def _is_esp_partition(partition):
    new_disk = attr.evolve(partition.device)
    new_disk._partitions = []
    if not can_be_boot_device(new_disk, with_reformatting=True):
        return False
    if partition.device.ptable == "gpt":
        return partition.flag == "boot"
    elif isinstance(partition.device, Disk):
        info = partition._info
        if info is None:
            return False
        typecode = info.raw.get("ID_PART_ENTRY_TYPE")
        if typecode is None:
            return False
        try:
            return int(typecode, 0) == 0xEF
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
