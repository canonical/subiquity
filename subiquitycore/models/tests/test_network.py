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

from subiquitycore.models.network import NetworkDev
from subiquitycore.tests import SubiTestCase


class TestRouteManagement(SubiTestCase):
    def setUp(self):
        self.nd = NetworkDev(None, None, None)
        self.ipv4s = [
            {"to": "default", "via": "10.0.2.2"},
            {"to": "1.2.3.0/24", "via": "1.2.3.4"},
        ]
        self.ipv6s = [
            {"to": "default", "via": "1111::2222"},
            {"to": "3333::0/64", "via": "3333::4444"},
        ]
        self.nd.config = {"routes": self.ipv4s + self.ipv6s}

    def test_remove_v4(self):
        self.nd.remove_routes(4)
        expected = self.ipv6s
        self.assertEqual(expected, self.nd.config["routes"])

    def test_remove_v6(self):
        self.nd.remove_routes(6)
        expected = self.ipv4s
        self.assertEqual(expected, self.nd.config["routes"])
