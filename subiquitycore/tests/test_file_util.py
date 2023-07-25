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

from subiquitycore.file_util import copy_file_if_exists
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
