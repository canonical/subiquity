import pytest

from . import assert_install_error


def test_bad_early(vmm):
    cc = """
      autoinstall:
        early-commands:
          - /bin/false
    """

    with assert_install_error():
        vmm.install(cloud_config=cc)


def test_invalid_source_id(vmm):
    cc = """
      source:
        id: invalid-id
    """

    with assert_install_error():
        vmm.install(cloud_config=cc)
