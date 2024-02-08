# Copyright 2024 Canonical, Ltd.
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

import os.path
import tempfile
import unittest
from unittest.mock import patch

from subiquitycore import ssh


class TestSSH(unittest.TestCase):
    @patch(
        "subiquitycore.ssh.host_key_fingerprints",
        return_value=[("key1-type", "key1-value"), ("key2-type", "key2-value")],
    )
    def test_host_key_info_premade(self, hkf):
        # premade fingerprints are present
        with tempfile.TemporaryDirectory(suffix="subiquity-ssh") as td:
            fpfile = os.path.join(td, "host-fingerprints.txt")
            with open(fpfile, "w") as outf:
                outf.write("mock host fingerprints")

            # fingerprints are pulled from the pre-made file
            self.assertEqual(
                ssh.host_key_info(runtime_state_dir=td), "mock host fingerprints"
            )

            # but are pulled from the system if the file is not there
            os.remove(fpfile)
            self.assertIn(
                "key1-type key1-value", ssh.host_key_info(runtime_state_dir=td)
            )

    @patch(
        "subiquitycore.ssh.host_key_fingerprints",
        return_value=[("key1-type", "key1-value"), ("key2-type", "key2-value")],
    )
    def test_host_key_info_query(self, hkf):
        self.assertIn("key1-type key1-value", ssh.host_key_info())
        self.assertIn("key2-type key2-value", ssh.host_key_info())
