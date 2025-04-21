
# vmtests

vmtests for subiquity work by way of virt-install and autoinstall.  SSH is
setup with a passwordless authentication key so that, both at install time and
first boot, the system under test can be automated and analyzed.

new vmtests look something like this.  See the VMM and VM classes in
`vmtests/tests/conftest.py` for more details and API.

```
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
```
