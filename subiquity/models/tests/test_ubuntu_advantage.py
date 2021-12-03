# Copyright 2021 Canonical, Ltd.
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

from subiquity.models.ubuntu_advantage import UbuntuAdvantageModel


class TestUbuntuAdvantageModel(unittest.TestCase):
    def test_make_cloudconfig_(self):
        model = UbuntuAdvantageModel()

        # Test with a token
        model.token = "0a1b2c3d4e5f6"
        expected = {
            "ubuntu_advantage": {
                "token": "0a1b2c3d4e5f6",
            }
        }
        self.assertEqual(model.make_cloudconfig(), expected)

        # Test without token
        model.token = ""
        self.assertEqual(model.make_cloudconfig(), {})
        model.token = None
        self.assertEqual(model.make_cloudconfig(), {})
