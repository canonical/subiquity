import pytest

from . import Firmware, GiB, MiB, assert_install_error


def test_bios_direct(vmm):
    test_config = """
      autoinstall:
        storage:
          layout:
            name: direct
    """

    sut = vmm.install(
        firmware=Firmware.BIOS,
        disk_sizes_GiB=[10],
        test_config=test_config,
    )

    [vda] = sut.lsblk()["blockdevices"]
    [vda1, vda2] = vda["children"]
    assert vda1["size"] == MiB
    assert vda2["size"] == 10 * GiB - 3 * MiB
    sut.reboot()

    sp = sut.ssh(["run-parts", "/etc/update-motd.d/"])
    print(sp.stdout.decode())
    sut.reboot()

    sp = sut.ssh(["run-parts", "/etc/update-motd.d/"])
    print(sp.stdout.decode())


def test_bad_early(vmm):
    test_config = """
      autoinstall:
        early-commands:
          - /bin/false
    """

    with assert_install_error():
        vmm.install(test_config=test_config)


def test_invalid_source_id(vmm):
    test_config = """
      source:
        id: invalid-id
    """

    with assert_install_error():
        vmm.install(firmware=Firmware.BIOS, test_config=test_config)
