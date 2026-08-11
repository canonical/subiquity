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

import contextlib
import logging
import shlex
from pathlib import Path

import attrs
import curtin.util

log = logging.getLogger("subiquity.common.os")


OS_RELEASE = Path("/etc/os-release")
OS_RELEASE_EXAMPLE = Path("examples/os-release-focal")

LEGACY_LSB_RELEASE = Path("/etc/lsb-release")
LEGACY_LSB_RELEASE_EXAMPLE = Path("examples/lsb-release-focal")


@attrs.define
class UbuntuInfo:
    # resolute, stonking, ...
    codename: str

    # x.y
    release: str

    # Ubuntu 25.10
    # Ubuntu 26.04 LTS
    # Ubuntu 24.04.4 LTS
    # Ubuntu Stonking Stingray (development branch)
    pretty_name: str

    def is_marked_lts(self) -> bool:
        """Tells whether the version of Ubuntu is marked LTS."""
        return "LTS" in self.pretty_name

    def version_number(self) -> tuple[int, int]:
        """Returns the release number as a sequence of integers."""
        major, minor = self.release.split(".")
        return int(major), int(minor)

    @classmethod
    def from_lsb_release(cls, path: Path) -> "UbuntuInfo":
        props: dict[str, str] = {}
        for tok in shlex.split(path.read_text()):
            k, _, v = tok.partition("=")
            if not v:
                # Empty value or .partition() did not find the separator.
                continue
            if not k.startswith("DISTRIB"):
                continue
            props[k] = v

        return UbuntuInfo(
            codename=props["DISTRIB_CODENAME"],
            release=props["DISTRIB_RELEASE"],
            pretty_name=props["DISTRIB_DESCRIPTION"],
        )

    @classmethod
    def from_os_release(cls, path: Path) -> "UbuntuInfo":
        props = curtin.util.load_os_release(path.read_text())
        return UbuntuInfo(
            codename=props["UBUNTU_CODENAME"],
            release=props["VERSION_ID"],
            pretty_name=props["PRETTY_NAME"],
        )


def lsb_release_from_path(path: Path) -> dict[str, str]:
    ret: dict[str, str] = {}

    content = path.read_text()

    for tok in shlex.split(content):
        k, _, v = tok.partition("=")
        if not k.startswith("DISTRIB_") or not v:
            continue
        ret[k.replace("DISTRIB_", "").lower()] = v
    return ret


def lsb_release(path: Path | None = None, dry_run: bool = False) -> dict[str, str]:
    """return a dictionary of values from /etc/lsb-release.
    keys are lower case with DISTRIB_ prefix removed."""
    if dry_run and path is not None:
        raise ValueError("Both dry_run and path are specified.")

    if path is None:
        path = LEGACY_LSB_RELEASE_EXAMPLE if dry_run else LEGACY_LSB_RELEASE

    return lsb_release_from_path(path)


def read_ubuntu_info(*, dry_run=False) -> UbuntuInfo:
    """Return Ubuntu information obtained either from our parsing
    implementation of /etc/os-release or legacy /etc/lsb-release (which is not
    present anymore in 26.10)."""
    os_release = OS_RELEASE
    legacy_lsb_release = LEGACY_LSB_RELEASE

    if dry_run:
        os_release = OS_RELEASE_EXAMPLE
        legacy_lsb_release = LEGACY_LSB_RELEASE_EXAMPLE

    with contextlib.suppress(FileNotFoundError):
        return UbuntuInfo.from_os_release(path=os_release)

    log.debug("cannot find os-release file, falling back to lsb-release")
    return UbuntuInfo.from_lsb_release(path=legacy_lsb_release)
