import contextlib
from enum import Enum, auto

import pytest

MiB = 1 << 20
GiB = 1 << 30


class Firmware:
    UEFI = "UEFI"
    BIOS = "BIOS"


@contextlib.contextmanager
def assert_install_error():
    with pytest.raises(pytest.fail.Exception) as ex:
        yield
    ex.match("install failed and reached ERROR state")
