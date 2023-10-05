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

from pathlib import Path
from unittest.mock import Mock, patch

from subiquitycore.file_util import (
    _DEF_GROUP,
    _DEF_PERMS_FILE,
    copy_file_if_exists,
    set_log_perms,
)
from subiquitycore.tests import SubiTestCase


class TestCopy(SubiTestCase):
    def test_copied_to_non_exist_dir(self):
        data = "stuff things"
        src = self.tmp_path("src")
        tgt = self.tmp_path("create-me/target")
        with open(src, "w") as fp:
            fp.write(data)
        copy_file_if_exists(src, tgt)
        self.assert_contents(tgt, data)

    def test_copied_non_exist_src(self):
        copy_file_if_exists("/does/not/exist", "/ditto")


@patch("subiquitycore.file_util.os.getuid", new=Mock(return_value=0))
class TestLogPerms(SubiTestCase):
    def setUp(self):
        chmod = patch("subiquitycore.file_util.os.chmod")
        self.chmod = chmod.start()
        self.addCleanup(chmod.stop)
        chown = patch("subiquitycore.file_util.os.chown")
        self.chown = chown.start()
        self.addCleanup(chown.stop)
        getgrnam = patch("subiquitycore.file_util.grp.getgrnam")
        self.getgrnam = getgrnam.start()
        self.addCleanup(getgrnam.stop)
        self.mock_gid = 10
        self.getgrnam.return_value = Mock(gr_gid=self.mock_gid)

    def test_defaults_group(self):
        target = self.tmp_dir()
        set_log_perms(target)
        self.getgrnam.assert_called_once_with(_DEF_GROUP)

    def test_defaults_file(self):
        target = self.tmp_path("file")
        Path(target).touch()
        set_log_perms(target)
        self.chmod.assert_called_once_with(target, _DEF_PERMS_FILE)
        self.chown.assert_called_once_with(target, 0, self.mock_gid)

    def test_defaults_dir(self):
        target = self.tmp_dir()
        set_log_perms(target)
        self.chmod.assert_called_once_with(target, _DEF_PERMS_FILE | 0o110)
        self.chown.assert_called_once_with(target, 0, self.mock_gid)

    def test_group_write_file(self):
        target = self.tmp_path("file")
        Path(target).touch()
        set_log_perms(target, group_write=True)
        self.chmod.assert_called_once_with(target, _DEF_PERMS_FILE | 0o020)
        self.chown.assert_called_once_with(target, 0, self.mock_gid)

    def test_group_write_dir(self):
        target = self.tmp_dir()
        set_log_perms(target, group_write=True)
        self.chmod.assert_called_once_with(target, _DEF_PERMS_FILE | 0o130)
        self.chown.assert_called_once_with(target, 0, self.mock_gid)

    def test_nogroup_write_file(self):
        target = self.tmp_path("file")
        Path(target).touch()
        set_log_perms(target, group_write=False)
        self.chmod.assert_called_once_with(target, _DEF_PERMS_FILE)
        self.chown.assert_called_once_with(target, 0, self.mock_gid)

    def test_nogroup_write_dir(self):
        target = self.tmp_dir()
        set_log_perms(target, group_write=False)
        self.chmod.assert_called_once_with(target, _DEF_PERMS_FILE | 0o110)
        self.chown.assert_called_once_with(target, 0, self.mock_gid)

    def test_mode_file(self):
        target = self.tmp_path("file")
        Path(target).touch()
        set_log_perms(target, mode=0o510)
        self.chmod.assert_called_once_with(target, 0o510)
        self.chown.assert_called_once_with(target, 0, self.mock_gid)

    def test_mode_dir(self):
        target = self.tmp_dir()
        set_log_perms(target, mode=0o510)
        self.chmod.assert_called_once_with(target, 0o510)
        self.chown.assert_called_once_with(target, 0, self.mock_gid)

    def test_group_file(self):
        self.getgrnam.return_value = Mock(gr_gid=11)
        target = self.tmp_path("file")
        Path(target).touch()
        set_log_perms(target, group="group1")
        self.chmod.assert_called_once_with(target, _DEF_PERMS_FILE)
        self.chown.assert_called_once_with(target, 0, 11)

    def test_group_dir(self):
        self.getgrnam.return_value = Mock(gr_gid=11)
        target = self.tmp_dir()
        set_log_perms(target, group="group1")
        self.chmod.assert_called_once_with(target, _DEF_PERMS_FILE | 0o110)
        self.chown.assert_called_once_with(target, 0, 11)
