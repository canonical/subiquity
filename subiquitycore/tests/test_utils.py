# Copyright 2022 Canonical, Ltd.
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

# from unittest.mock import Mock

from subiquitycore.tests import SubiTestCase
from subiquitycore.utils import _zsys_uuid_charset, gen_zsys_uuid, orig_environ


class TestOrigEnviron(SubiTestCase):
    def test_empty(self):
        env = {}
        expected = env
        self.assertEqual(expected, orig_environ(env))

    def test_orig_path(self):
        env = {"PATH": "a", "PATH_ORIG": "b"}
        expected = {"PATH": "b"}
        self.assertEqual(expected, orig_environ(env))

    def test_not_this_key(self):
        env = {"PATH": "a", "PATH_ORIG_AAAAA": "b"}
        expected = env
        self.assertEqual(expected, orig_environ(env))

    def test_remove_empty_key(self):
        env = {"STUFF": "a", "STUFF_ORIG": ""}
        expected = {}
        self.assertEqual(expected, orig_environ(env))

    def test_no_ld_library_path(self):
        env = {"LD_LIBRARY_PATH": "a"}
        expected = {}
        self.assertEqual(expected, orig_environ(env))

    def test_practical(self):
        snap = "/snap/subiquity/1234"
        env = {
            "TERM": "linux",
            "LD_LIBRARY_PATH": "/var/lib/snapd/lib/gl",
            "PYTHONIOENCODING_ORIG": "",
            "PYTHONIOENCODING": "utf-8",
            "SUBIQUITY_ROOT_ORIG": "",
            "SUBIQUITY_ROOT": snap,
            "PYTHON_ORIG": "",
            "PYTHON": f"{snap}/usr/bin/python3.10",
            "PYTHONPATH_ORIG": "",
            "PYTHONPATH": f"{snap}/stuff/things",
            "PY3OR2_PYTHON_ORIG": "",
            "PY3OR2_PYTHON": f"{snap}/usr/bin/python3.10",
            "PATH_ORIG": "/usr/bin:/bin",
            "PATH": "/usr/bin:/bin:/snap/bin",
        }
        expected = {
            "TERM": "linux",
            "PATH": "/usr/bin:/bin",
        }
        self.assertEqual(expected, orig_environ(env))


class TestZsysUUID(SubiTestCase):
    def test_charset(self):
        charset = _zsys_uuid_charset()
        for c in "0", "9", "a", "z":
            self.assertIn(c, charset)
        bads = [
            chr(ord("0") - 1),
            chr(ord("9") + 1),
            chr(ord("a") - 1),
            chr(ord("z") + 1),
        ]
        for c in bads:
            self.assertNotIn(c, charset)

    def test_zsys_uuid(self):
        for i in range(10):
            uuid = gen_zsys_uuid()
            self.assertEqual(6, len(uuid), uuid)
