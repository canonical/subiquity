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

from typing import Optional
from unittest.mock import Mock, patch

import attr

from subiquity.server.pkghelper import PackageInstaller, PackageInstallState
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app


@patch("apt.Cache", Mock(return_value={}))
class TestPackageInstaller(SubiTestCase):
    class Package:
        @attr.s(auto_attribs=True)
        class Candidate:
            uri: str

        def __init__(
            self, installed: bool, name: str, candidate_uri: Optional[str] = None
        ) -> None:
            self.installed = installed
            self.name = name
            if candidate_uri is None:
                self.candidate = None
            else:
                self.candidate = self.Candidate(uri=candidate_uri)

    def setUp(self):
        self.pkginstaller = PackageInstaller(make_app())

    async def test_install_pkg_not_found(self):
        self.assertEqual(
            await self.pkginstaller.install_pkg("sysvinit-core"),
            PackageInstallState.NOT_AVAILABLE,
        )

    async def test_install_pkg_already_installed(self):
        with patch.dict(
            self.pkginstaller.cache,
            {"util-linux": self.Package(installed=True, name="util-linux")},
        ):
            self.assertEqual(
                await self.pkginstaller.install_pkg("util-linux"),
                PackageInstallState.DONE,
            )

    async def test_install_pkg_dr_install(self):
        with patch.dict(
            self.pkginstaller.cache,
            {"python3-attr": self.Package(installed=False, name="python3-attr")},
        ):
            with patch("subiquity.server.pkghelper.asyncio.sleep") as sleep:
                self.assertEqual(
                    await self.pkginstaller.install_pkg("python3-attr"),
                    PackageInstallState.DONE,
                )
        sleep.assert_called_once()

    async def test_install_pkg_not_from_cdrom(self):
        with patch.dict(
            self.pkginstaller.cache,
            {
                "python3-attr": self.Package(
                    installed=False,
                    name="python3-attr",
                    candidate_uri="http://archive.ubuntu.com",
                )
            },
        ):
            with patch.object(self.pkginstaller.app.opts, "dry_run", False):
                self.assertEqual(
                    await self.pkginstaller.install_pkg("python3-attr"),
                    PackageInstallState.NOT_AVAILABLE,
                )

    async def test_install_pkg_alternative_impl(self):
        async def impl(pkgname: str) -> PackageInstallState:
            return PackageInstallState.FAILED

        with patch.object(self.pkginstaller, "_install_pkg") as default_impl:
            self.assertEqual(
                await self.pkginstaller.install_pkg("python3-attr", install_coro=impl),
                PackageInstallState.FAILED,
            )

        default_impl.assert_not_called()
