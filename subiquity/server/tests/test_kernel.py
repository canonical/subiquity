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
import unittest
from unittest import mock

from subiquity.server.kernel import flavor_to_pkgname, list_installed_kernels


class TestFlavorToPkgname(unittest.TestCase):
    def test_flavor_generic(self):
        self.assertEqual("linux-generic", flavor_to_pkgname("generic", dry_run=True))

    def test_flavor_oem(self):
        self.assertEqual("linux-oem-20.04", flavor_to_pkgname("oem", dry_run=True))

    def test_flavor_hwe(self):
        self.assertEqual(
            "linux-generic-hwe-20.04", flavor_to_pkgname("hwe", dry_run=True)
        )

        self.assertEqual(
            "linux-generic-hwe-20.04", flavor_to_pkgname("generic-hwe", dry_run=True)
        )


class TestListInstalledKernels(unittest.IsolatedAsyncioTestCase):
    async def test_one_kernel(self):
        rv = subprocess.CompletedProcess([], 0)
        rv.stdout = "linux-image-6.1.0-16-generic"
        with mock.patch(
            "subiquity.server.kernel.arun_command", return_value=rv
        ) as mock_arun:
            ret = await list_installed_kernels("/")
            self.assertEqual(["linux-image-6.1.0-16-generic"], ret)
        mock_arun.assert_called_once()

    async def test_two_kernels(self):
        rv = subprocess.CompletedProcess([], 0)
        rv.stdout = """\
linux-image-6.1.0-16-generic
linux-image-6.2.0-24-generic
"""
        with mock.patch(
            "subiquity.server.kernel.arun_command", return_value=rv
        ) as mock_arun:
            ret = await list_installed_kernels("/")
            self.assertEqual(
                ["linux-image-6.1.0-16-generic", "linux-image-6.2.0-24-generic"], ret
            )
        mock_arun.assert_called_once()

    async def test_no_kernel(self):
        rv = subprocess.CompletedProcess([], 0)
        rv.stdout = "\n"
        with mock.patch(
            "subiquity.server.kernel.arun_command", return_value=rv
        ) as mock_arun:
            ret = await list_installed_kernels("/")
            self.assertEqual([], ret)
        mock_arun.assert_called_once()
