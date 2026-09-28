import pytest
import yaml

from . import Firmware, GiB, MiB, assert_install_error


def test_bios_direct(vmm):
    # please keep this test simple, it's meant to be an introduction to the
    # concept.
    cc = """
      autoinstall:
        storage:
          layout:
            name: direct
    """

    sut = vmm.install(
        firmware=Firmware.BIOS,
        disk_sizes_GiB=[10],
        cloud_config=cc,
    )

    [vda] = sut.lsblk()["blockdevices"]
    [vda1, vda2] = vda["children"]
    assert vda1["size"] == MiB
    assert vda2["size"] == 10 * GiB - 3 * MiB


def test_uefi_direct(vmm):
    # the UEFI layout adds an ESP (mounted at /boot/efi) ahead of the root
    # partition.  For a 10 GiB disk the ESP is sized to its minimum of
    # 538 MiB, leaving the rest for root.
    cc = """
      autoinstall:
        storage:
          layout:
            name: direct
    """

    sut = vmm.install(
        firmware=Firmware.UEFI,
        disk_sizes_GiB=[10],
        cloud_config=cc,
    )

    [vda] = sut.lsblk()["blockdevices"]
    [vda1, vda2] = vda["children"]
    assert vda1["size"] == 538 * MiB
    assert vda2["size"] == 10 * GiB - 540 * MiB
