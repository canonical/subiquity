# Copyright 2023 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import pathlib
import subprocess
from typing import List

from subiquitycore.lsb_release import lsb_release
from subiquitycore.utils import arun_command


def flavor_to_pkgname(flavor: str, *, dry_run: bool) -> str:
    if flavor == "generic":
        return "linux-generic"
    if flavor == "hwe":
        flavor = "generic-hwe"

    release = lsb_release(dry_run=dry_run)["release"]
    # Should check this package exists really but
    # that's a bit tricky until we get cleverer about
    # the apt config in general.
    return f"linux-{flavor}-{release}"


async def list_installed_kernels(rootfs: pathlib.Path) -> List[str]:
    """Return the list of linux-image packages installed in rootfs."""
    # TODO use python-apt instead coupled with rootdir.
    # Ideally, we should not hardcode var/lib/dpkg/status which is an
    # implementation detail.
    try:
        cp = await arun_command(
            [
                "grep-status",
                "--whole-pkg",
                "-FProvides",
                "linux-image",
                "--and",
                "-FStatus",
                "installed",
                "--show-field=Package",
                "--no-field-names",
                str(rootfs / pathlib.Path("var/lib/dpkg/status")),
            ],
            check=True,
        )
    except subprocess.CalledProcessError as cpe:
        # grep-status exits with status 1 when there is no match.
        if cpe.returncode != 1:
            raise
        stdout = cpe.stdout
    else:
        stdout = cp.stdout

    return [line for line in stdout.splitlines() if line]
