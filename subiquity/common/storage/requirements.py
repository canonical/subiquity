# Copyright 2026 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import enum
from collections.abc import Callable
from typing import TYPE_CHECKING

import attrs

from subiquity.common.os import read_ubuntu_info

if TYPE_CHECKING:
    # Avoid circular import: models/storage.py imports Requirements
    # from this module at the top level.
    from subiquity.models.storage import StorageModel


class RequirementSeverity(enum.Enum):
    """How seriously a violated requirement should be treated."""

    BLOCKING = "blocking"
    WARNING = "warning"


class GuidanceMessageKind(enum.Enum):
    """User-facing guidance messages shown when a storage requirement is
    violated.

    Use the member (e.g. ``GuidanceMessageKind.MOUNT_ROOT``) in APIs and wire
    protocols — the member's **key** is the stable identifier.  The
    ``.value`` is a locale-dependent translated string and **must not**
    be sent over the API or stored in configuration.
    """

    MOUNT_ROOT = _("Mount a filesystem at /")
    MOUNT_LOCAL_BOOT = _("Mount a local filesystem at /boot")
    SELECT_BOOT_DISK = _("Select a boot disk")
    USE_EXT4_BOOT = _("Use the ext4 filesystem for /boot")
    BOOT_ON_SIMPLE_SETUP = _("Place /boot on a partition of a disk (or RAID 1 disk)")


@attrs.define
class StorageRequirement:
    """A single install-readiness check with a user-facing guidance message.

    Attributes
    ----------
    guidance_message_kind:
        Enum member identifying the kind of guidance message to show the user
        when the requirement is violated.  The enum's ``.value`` is a
        locale-dependent translated string.
    severity:
        Whether a violation blocks installation or is merely advisory.
    check:
        Callable that returns True when the requirement is satisfied.
    applies_to:
        Callable that returns True when this requirement is relevant for
        the current system configuration.  Defaults to always applicable.
    """

    guidance_message_kind: GuidanceMessageKind
    severity: RequirementSeverity
    check: Callable[["StorageModel"], bool]
    applies_to: Callable[["StorageModel"], bool] = lambda m: True

    def is_applicable(self, model) -> bool:
        """Return True if this requirement applies to the given model."""
        return self.applies_to(model)

    def is_satisfied(self, model) -> bool:
        """Return True if this requirement's condition is met."""
        return self.check(model)

    def is_violated(self, model) -> bool:
        """Return True when this requirement applies but is not satisfied."""
        return self.is_applicable(model) and not self.is_satisfied(model)


def _is_boot_ext4(model) -> bool:
    """Return True when /boot (or / if no separate boot) uses the ext4
    filesystem.  Only meaningful on GRUB-based architectures where ext4
    is the validated boot filesystem.  Other filesystems that GRUB
    supports (ext2, ext3, FAT, ISO9660, ...) are not validated here."""
    mount = model._mount_for_path("/boot", parent_ok=True)
    if mount is None:
        return False
    return mount.fstype == "ext4"


def _is_boot_on_simple_setup(model) -> bool:
    """Signed GRUB on 26.10+ can only boot from simple storage setups.

    The /boot filesystem (or / if /boot is not mounted separately) must
    sit on one of the following, and nothing else:
    * a directly-formatted disk
    * a partition on a disk
    * a RAID 1 (optionally with partitions on top)

    Any other volume type is rejected: LVM (volume groups and logical
    volumes), LUKS/dm-crypt, ZFS (zpools and datasets), non-RAID-1 RAID
    levels, and arbitrary devices.

    Walks the full storage chain backing the /boot mount and checks that
    every element is one of the accepted types (and that any RAID is
    level 1).

    See https://discourse.ubuntu.com/t/streamlining-secure-boot-for-26-10/79069
    """
    mount = model._mount_for_path("/boot", parent_ok=True)
    if mount is None:
        return False

    # Deferred import: subiquity.models.storage imports this module at top
    # level, so importing it here avoids a circular import at module load.
    from subiquity.models.storage import Disk, Filesystem, Mount, Partition, Raid

    accepted = (Disk, Filesystem, Mount, Partition, Raid)
    for element in mount.iter_storage_chain():
        if not isinstance(element, accepted):
            return False
        if isinstance(element, Raid) and element.raidlevel != "raid1":
            return False
    return True


def _uses_signed_grub_26_10(model) -> bool:
    """UEFI systems with signed GRUB require ext4 for /boot on 26.10+."""
    if not model.is_root_mounted() or not model.uses_signed_grub():
        return False
    version_number = read_ubuntu_info(dry_run=model.dry_run).version_number()
    return version_number >= (26, 10)


class Requirements:
    """Well-known install-readiness checks for storage setup.

    Each class attribute is a named ``StorageRequirement`` instance.
    Use ``Requirements.all()`` to iterate over every registered requirement.
    """

    ROOT_MOUNTED = StorageRequirement(
        guidance_message_kind=GuidanceMessageKind.MOUNT_ROOT,
        severity=RequirementSeverity.BLOCKING,
        check=lambda m: m.is_root_mounted(),
    )
    REMOTE_BOOT_LOCAL = StorageRequirement(
        guidance_message_kind=GuidanceMessageKind.MOUNT_LOCAL_BOOT,
        severity=RequirementSeverity.BLOCKING,
        check=lambda m: m.is_boot_mounted() and not m.is_bootfs_on_remote_storage(),
        applies_to=lambda m: m.is_root_mounted()
        and m.is_rootfs_on_remote_storage()
        and not m.supports_nvme_tcp_booting,
    )
    BOOTLOADER_NEEDED = StorageRequirement(
        guidance_message_kind=GuidanceMessageKind.SELECT_BOOT_DISK,
        severity=RequirementSeverity.BLOCKING,
        check=lambda m: not m.needs_bootloader_partition(),
    )
    BOOT_EXT4 = StorageRequirement(
        guidance_message_kind=GuidanceMessageKind.USE_EXT4_BOOT,
        severity=RequirementSeverity.BLOCKING,
        check=_is_boot_ext4,
        applies_to=_uses_signed_grub_26_10,
    )
    # This requirement could be merged with BOOT_EXT4, but the resulting error
    # message would become a bit vague.
    BOOT_ON_SIMPLE_SETUP = StorageRequirement(
        guidance_message_kind=GuidanceMessageKind.BOOT_ON_SIMPLE_SETUP,
        severity=RequirementSeverity.BLOCKING,
        check=_is_boot_on_simple_setup,
        applies_to=_uses_signed_grub_26_10,
    )

    @staticmethod
    def all() -> list[StorageRequirement]:
        """Return every registered requirement in evaluation order."""
        return [
            Requirements.ROOT_MOUNTED,
            Requirements.REMOTE_BOOT_LOCAL,
            Requirements.BOOTLOADER_NEEDED,
            Requirements.BOOT_EXT4,
            Requirements.BOOT_ON_SIMPLE_SETUP,
        ]
