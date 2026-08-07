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

import unittest
from pathlib import Path
from unittest.mock import patch

from subiquitycore.os import (
    LEGACY_LSB_RELEASE,
    LEGACY_LSB_RELEASE_EXAMPLE,
    UbuntuInfo,
    lsb_release,
    read_ubuntu_info,
)


class TestUbuntuInfo(unittest.TestCase):
    def test_from_lsb_release(self):
        content = Path("examples/lsb-release-resolute").read_text()

        with patch("subiquitycore.os.Path.read_text", return_value=content):
            info = UbuntuInfo.from_lsb_release(path=Path("/dev/null"))

        self.assertEqual("resolute", info.codename)
        self.assertEqual("26.04", info.release)
        self.assertEqual("Ubuntu 26.04 LTS", info.pretty_name)

    def test_from_os_release(self):
        content = Path("examples/os-release-resolute").read_text()

        with patch("subiquitycore.os.Path.read_text", return_value=content):
            info = UbuntuInfo.from_os_release(path=Path("/dev/null"))

        self.assertEqual("resolute", info.codename)
        self.assertEqual("26.04", info.release)
        self.assertEqual("Ubuntu 26.04 LTS", info.pretty_name)


class TestLSBRelease(unittest.TestCase):
    def setUp(self):
        self.lsb_str = """
DISTRIB_ID=Ubuntu
DISTRIB_RELEASE=21.10
DISTRIB_CODENAME=impish
DISTRIB_DESCRIPTION="Ubuntu 21.10"
        """

    def test_lsb_release(self):
        with patch.object(Path, "read_text", autospec=True, return_value=self.lsb_str):
            distro = lsb_release(path=Path("sample"))

        self.assertEqual(distro["id"], "Ubuntu")
        self.assertEqual(distro["release"], "21.10")
        self.assertEqual(distro["codename"], "impish")
        self.assertEqual(distro["description"], "Ubuntu 21.10")

    def test_lsb_release_inexistent(self):
        with patch.object(
            Path, "read_text", autospec=True, side_effect=FileNotFoundError
        ) as patched:
            with self.assertRaises(FileNotFoundError):
                lsb_release(Path("/inexistent"))
        self.assertEqual(Path("/inexistent"), patched.call_args.args[0])

    def test_lsb_release_default(self):
        with patch.object(
            Path, "read_text", autospec=True, return_value=self.lsb_str
        ) as patched:
            lsb_release(path=None)
        self.assertEqual(LEGACY_LSB_RELEASE, patched.call_args.args[0])

    def test_lsb_release_dry_run(self):
        with patch.object(
            Path, "read_text", autospec=True, return_value=self.lsb_str
        ) as patched:
            lsb_release(dry_run=True)
        self.assertEqual(LEGACY_LSB_RELEASE_EXAMPLE, patched.call_args.args[0])

    def test_lsb_release_mutually_exclusive(self):
        with self.assertRaises(ValueError):
            lsb_release(path=Path("sample"), dry_run=True)


class TestReadUbuntuInfo(unittest.TestCase):
    resolute = UbuntuInfo(
        codename="resolute",
        release="26.04",
        pretty_name="Ubuntu 26.04 LTS",
    )

    @patch.object(UbuntuInfo, "from_os_release", return_value=resolute)
    @patch.object(UbuntuInfo, "from_lsb_release", return_value=resolute)
    def test_os_release_exists(self, m_lsb_release, m_os_release):
        self.assertEqual(self.resolute, read_ubuntu_info())

        m_os_release.assert_called_once_with(path=Path("/etc/os-release"))
        m_lsb_release.assert_not_called()

    @patch.object(UbuntuInfo, "from_os_release", side_effect=FileNotFoundError)
    @patch.object(UbuntuInfo, "from_lsb_release", return_value=resolute)
    def test_only_lsb_release_exists(self, m_lsb_release, m_os_release):
        self.assertEqual(self.resolute, read_ubuntu_info())

        m_os_release.assert_called_once_with(path=Path("/etc/os-release"))
        m_lsb_release.assert_called_once_with(path=Path("/etc/lsb-release"))

    @patch.object(UbuntuInfo, "from_os_release", side_effect=FileNotFoundError)
    @patch.object(UbuntuInfo, "from_lsb_release", side_effect=FileNotFoundError)
    def test_none_exists(self, m_lsb_release, m_os_release):
        with self.assertRaises(FileNotFoundError):
            read_ubuntu_info()

        m_os_release.assert_called_once_with(path=Path("/etc/os-release"))
        m_lsb_release.assert_called_once_with(path=Path("/etc/lsb-release"))
