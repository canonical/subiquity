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

import unittest

from subiquity.models.tests.test_filesystem import (
    make_model_and_disk,
    )

from subiquity.common.filesystem import gaps


class TestGaps(unittest.TestCase):
    def test_basic(self):
        model, disk1 = make_model_and_disk()

        pg = gaps.parts_and_gaps(disk1)
        self.assertEqual(1, len(pg))
        self.assertTrue(isinstance(pg[0], gaps.Gap))
        self.assertEqual(1024 * 1024, pg[0].offset)
