import pytest

from . import assert_install_error


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
        vmm.install(test_config=test_config)
