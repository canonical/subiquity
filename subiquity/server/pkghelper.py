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

import asyncio
import logging
import os
from typing import Dict, Optional

import apt

from subiquity.common.types import PackageInstallState
from subiquitycore.utils import arun_command

log = logging.getLogger("subiquity.server.pkghelper")


class PackageInstaller:
    """Install packages from the pool on the ISO in the live session.

    Sometimes we need packages from the pool in the live session, for
    example to install wpasupplicant when wlan interfaces are detected
    by the server installer.
    """

    def __init__(self):
        self.pkgs: Dict[str, asyncio.Task] = {}
        self._cache: Optional[apt.Cache] = None

    @property
    def cache(self):
        if self._cache is None:
            self._cache = apt.Cache()
        return self._cache

    def state_for_pkg(self, pkgname: str) -> PackageInstallState:
        t = self.pkgs.get(pkgname)
        if t is None:
            return PackageInstallState.NOT_NEEDED
        if t.done():
            return t.result()
        else:
            return PackageInstallState.INSTALLING

    def start_installing_pkg(self, pkgname: str) -> None:
        if pkgname not in self.pkgs:
            self.pkgs[pkgname] = asyncio.create_task(self._install_pkg(pkgname))

    async def install_pkg(self, pkgname) -> PackageInstallState:
        self.start_installing_pkg(pkgname)
        return await self.pkgs[pkgname]

    async def _install_pkg(self, pkgname: str) -> PackageInstallState:
        log.debug("checking if %s is available", pkgname)
        binpkg = self.cache.get(pkgname)
        if not binpkg:
            log.debug("%s not found", pkgname)
            return PackageInstallState.NOT_AVAILABLE
        if binpkg.installed:
            log.debug("%s already installed", pkgname)
            return PackageInstallState.DONE
        if not binpkg.candidate.uri.startswith("cdrom:"):
            log.debug(
                "%s not available from cdrom (rather %s)", pkgname, binpkg.candidate.uri
            )
            return PackageInstallState.NOT_AVAILABLE
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        apt_opts = [
            "--quiet",
            "--assume-yes",
            "--option=Dpkg::Options::=--force-unsafe-io",
            "--option=Dpkg::Options::=--force-confold",
        ]
        cp = await arun_command(["apt-get", "install"] + apt_opts + [pkgname], env=env)
        log.debug("apt-get install %s returned %s", pkgname, cp)
        if cp.returncode == 0:
            return PackageInstallState.DONE
        else:
            return PackageInstallState.FAILED
