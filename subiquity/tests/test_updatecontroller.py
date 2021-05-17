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

from subiquity.server.controllers.updates import UpdatesController
from subiquity.tests.mocks import make_app
from subiquitycore.tests import SubiTestCase


class TestUpdateController(SubiTestCase):

    def setUp(self):
        self.uc = UpdatesController(make_app())

    def test_good_values(self):
        goods = [
            'security',
            'all',
        ]
        for g in goods:
            self.uc.deserialize(g)

    def test_bad_values(self):
        bads = [
            'none',  # a value that was discussed but not used
            'notanupdatepolicy',
        ]
        for b in bads:
            with self.assertRaises(ValueError):
                self.uc.deserialize(b)
