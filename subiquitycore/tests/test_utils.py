# Copyright 2022 Canonical, Ltd.
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

# from unittest.mock import Mock

from subiquitycore.tests import SubiTestCase
from subiquitycore.utils import orig_environ


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
