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

if TYPE_CHECKING:
    # Avoid circular import: models/filesystem.py imports Requirements
    # from this module at the top level.
    from subiquity.models.filesystem import FilesystemModel


class RequirementSeverity(enum.Enum):
    """How seriously a violated requirement should be treated."""

    BLOCKING = "blocking"
    WARNING = "warning"


@attrs.define
class StorageRequirement:
    """A single install-readiness check with a user-facing guidance message.

    Attributes
    ----------
    guidance_message:
        Translatable string shown to the user when the requirement is violated.
    severity:
        Whether a violation blocks installation or is merely advisory.
    check:
        Callable that returns True when the requirement is satisfied.
    applies_to:
        Callable that returns True when this requirement is relevant for
        the current system configuration.  Defaults to always applicable.
    """

    guidance_message: str
    severity: RequirementSeverity
    check: Callable[["FilesystemModel"], bool]
    applies_to: Callable[["FilesystemModel"], bool] = lambda m: True

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


class Requirements:
    """Well-known install-readiness checks for storage setup.

    Each class attribute is a named ``StorageRequirement`` instance.
    Use ``Requirements.all()`` to iterate over every registered requirement.
    """

    ROOT_MOUNTED = StorageRequirement(
        guidance_message=_("Mount a filesystem at /"),
        severity=RequirementSeverity.BLOCKING,
        check=lambda m: m.is_root_mounted(),
    )
    REMOTE_BOOT_LOCAL = StorageRequirement(
        guidance_message=_("Mount a local filesystem at /boot"),
        severity=RequirementSeverity.BLOCKING,
        check=lambda m: m.is_boot_mounted() and not m.is_bootfs_on_remote_storage(),
        applies_to=lambda m: m.is_root_mounted()
        and m.is_rootfs_on_remote_storage()
        and not m.supports_nvme_tcp_booting,
    )
    BOOTLOADER_NEEDED = StorageRequirement(
        guidance_message=_("Select a boot disk"),
        severity=RequirementSeverity.BLOCKING,
        check=lambda m: not m.needs_bootloader_partition(),
    )
    BOOT_FILESYSTEM = StorageRequirement(
        guidance_message=_("Use the ext4 filesystem for /boot"),
        severity=RequirementSeverity.BLOCKING,
        check=_is_boot_ext4,
        applies_to=lambda m: m.is_root_mounted() and m.uses_signed_grub(),
    )

    @staticmethod
    def all() -> list[StorageRequirement]:
        """Return every registered requirement in evaluation order."""
        return [
            Requirements.ROOT_MOUNTED,
            Requirements.REMOTE_BOOT_LOCAL,
            Requirements.BOOTLOADER_NEEDED,
            Requirements.BOOT_FILESYSTEM,
        ]
