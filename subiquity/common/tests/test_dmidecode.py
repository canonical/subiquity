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

import unittest
from subprocess import CompletedProcess
from unittest import mock

from subiquity.common.dmidecode import dmidecode_get


class TestDmidecode(unittest.TestCase):
    @mock.patch("subiquity.common.dmidecode.run_command")
    def test_fail(self, run_cmd):
        run_cmd.return_value = CompletedProcess([], 1)
        self.assertEqual("", dmidecode_get("invalid-key"))

    @mock.patch("subiquity.common.dmidecode.run_command")
    def test_poweredge(self, run_cmd):
        expected = "PowerEdge R6525"
        run_cmd.return_value = CompletedProcess([], 0, stdout=expected)
        self.assertEqual(expected, dmidecode_get("system-product-name"))
