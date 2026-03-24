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

import subprocess
from typing import Optional
from unittest.mock import Mock, patch

import attr

from subiquity.server.pkghelper import (
    DryRunPackageInstaller,
    PackageInstaller,
    PackageInstallState,
)
from subiquity.server.pkghelper import log as PkgHelperLogger
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


class MockPackage:
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


@patch("apt.Cache", Mock(return_value={}))
class TestPackageInstaller(SubiTestCase):
    def setUp(self):
        self.pkginstaller = PackageInstaller()

    @parameterized.expand(
        (
            (
                "http://archive.ubuntu.com/ubuntu/pool/main/w/wpa/wpasupplicant_2.11-0ubuntu5_amd64.deb",  # noqa
                False,
                PackageInstallState.NOT_AVAILABLE,
            ),
            (
                "cdrom://Ubuntu-Server 25.10 _Questing Quokka_ - Release amd64 (20251007.1)/pool/main/wpasupplicant_2%253a2.11-0ubuntu4_amd64.deb",  # noqa
                True,
                PackageInstallState.DONE,
            ),
            (
                "file:/cdrom/pool/main/w/wpa/wpasupplicant_2%253a2.11-0ubuntu5_amd64.deb",
                True,
                PackageInstallState.DONE,
            ),
            (
                "file:/cdrom/pool/main/w/wpa/wpasupplicant_2%253a2.11-0ubuntu5_amd64.deb",
                False,
                PackageInstallState.FAILED,
            ),
        ),
    )
    async def test_install_pkg(
        self,
        candidate_uri: str,
        install_succeeds: bool,
        expected_state: PackageInstallState,
    ):
        with patch.dict(
            self.pkginstaller.cache,
            {
                "wpasupplicant": MockPackage(
                    installed=False,
                    name="wpasupplicant",
                    candidate_uri=candidate_uri,
                )
            },
        ):
            with patch(
                "subiquity.server.pkghelper.arun_command",
                return_value=subprocess.CompletedProcess(
                    [], 0 if install_succeeds else 1
                ),
            ):
                self.assertEqual(
                    expected_state,
                    await self.pkginstaller.install_pkg("wpasupplicant"),
                )

    async def test_install_pkg_not_found(self):
        self.assertEqual(
            await self.pkginstaller.install_pkg("sysvinit-core"),
            PackageInstallState.NOT_AVAILABLE,
        )

    async def test_install_pkg_already_installed(self):
        with patch.dict(
            self.pkginstaller.cache,
            {"util-linux": MockPackage(installed=True, name="util-linux")},
        ):
            self.assertEqual(
                await self.pkginstaller.install_pkg("util-linux"),
                PackageInstallState.DONE,
            )


@patch("apt.Cache", Mock(return_value={}))
@patch("subiquity.server.pkghelper.asyncio.sleep")
class TestDryRunPackageInstaller(SubiTestCase):
    def setUp(self):
        app = make_app()
        app.debug_flags = []
        self.pkginstaller = DryRunPackageInstaller(app)

    async def test_install_pkg(self, sleep):
        with patch.dict(
            self.pkginstaller.cache,
            {"python3-attr": MockPackage(installed=False, name="python3-attr")},
        ):
            with self.assertLogs(PkgHelperLogger, "DEBUG") as debug:
                self.assertEqual(
                    await self.pkginstaller.install_pkg("python3-attr"),
                    PackageInstallState.DONE,
                )
        sleep.assert_called_once()
        self.assertIn(
            "dry-run apt-get install %s", [record.msg for record in debug.records]
        )

    async def test_install_pkg_wpasupplicant_default_impl(self, sleep):
        with patch.object(self.pkginstaller, "debug_flags", []):
            self.assertEqual(
                await self.pkginstaller.install_pkg("wpasupplicant"),
                PackageInstallState.DONE,
            )
        sleep.assert_called_once()

    async def test_install_pkg_wpasupplicant_done(self, sleep):
        with patch.object(self.pkginstaller, "debug_flags", ["wlan_install=DONE"]):
            self.assertEqual(
                await self.pkginstaller.install_pkg("wpasupplicant"),
                PackageInstallState.DONE,
            )
        sleep.assert_called_once()

    async def test_install_pkg_wpasupplicant_failed(self, sleep):
        with patch.object(self.pkginstaller, "debug_flags", ["wlan_install=FAILED"]):
            self.assertEqual(
                await self.pkginstaller.install_pkg("wpasupplicant"),
                PackageInstallState.FAILED,
            )
        sleep.assert_called_once()
