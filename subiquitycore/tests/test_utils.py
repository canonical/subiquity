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

import os
from unittest.mock import patch

from subiquitycore.tests import SubiTestCase
from subiquitycore.utils import (
    _zsys_uuid_charset,
    crypt_password,
    gen_zsys_uuid,
    orig_environ,
    system_scripts_env,
)


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


class TestSystemScriptsEnv(SubiTestCase):
    def test_path_no_snap_usr_bin(self):
        """Test path to /<snap>/usr/bin/ is not present.

        This makes sure that the snap python is not picked up.
        """
        snap = "/snap/subiquity/current"
        snap_env = {
            "SNAP": snap,
            "PATH_ORIG": "/usr/bin",
            "PATH": f"{snap}/usr/bin",
        }

        with patch.dict(os.environ, snap_env, clear=True):
            path = system_scripts_env()["PATH"]

        self.assertNotIn(f"{snap}/usr/bin", path)

    def test_path_scripts_location(self):
        """Test system_scripts path location for Desktop and Server."""
        snap = "/snap/subiquity/current"
        snap_env = {
            "SNAP": snap,
            "PATH_ORIG": "/usr/bin",
            "PATH": f"{snap}/usr/bin:{snap}/bin",
        }

        with patch.dict(os.environ, snap_env, clear=True):
            path = system_scripts_env()["PATH"]

        self.assertIn(f"{snap}/system_scripts", path)
        self.assertIn(f"{snap}/bin/subiquity/system_scripts", path)


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


class TestCryptPassword(SubiTestCase):
    @patch("passlib.utils.handlers.HasSalt._generate_salt")
    def test_canary_output_changed(self, salt_mock):
        """Test known outputs to track any changes to hash function"""
        # Test SHA-512
        salt_mock.return_value = "mock.salt"
        python = crypt_password("ubuntu", "SHA-512")
        known = (
            "$6$mock.salt$5fMmG3oLeOGZj9yRgVj3oVyF4zmNy10dZ0rI7mKf4tHW3WE8JPk."
            "dpXKMAVhYfmh7ccQIRSKp.b0wqKQ8us5S1"
        )
        self.assertEqual(python, known)

        # Test SHA-256
        salt_mock.return_value = "mock.salt"
        python = crypt_password("ubuntu", "SHA-256")
        known = "$5$mock.salt$mVAnp2L7zhx8JgnO5NU0D6q0aSnaWa3f3uMvJQAgBIC"
        self.assertEqual(python, known)

        # Test MD5
        salt_mock.return_value = "mock.sal"
        python = crypt_password("ubuntu", "MD5")
        known = "$1$mock.sal$daGoQL9mCvUkkwtK5kJML0"
        self.assertEqual(python, known)

        # Test DES
        salt_mock.return_value = "mo"
        python = crypt_password("ubuntu", "DES")
        known = "mohjxgnj7QHfQ"
        self.assertEqual(python, known)

    def test_exception_on_unknown_algorithm(self):
        """Test an exception is thrown when an unknown algorithm is requested."""
        with self.assertRaises(Exception):
            crypt_password("mock_passwd", algo="UNKNOWN")
