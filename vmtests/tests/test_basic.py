import pytest

from . import Firmware, GiB, MiB, assert_install_error


def test_bios_direct(vmm):
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
