# Copyright 2023 Canonical, Ltd.
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
from unittest.mock import Mock

from subiquitycore.controllers.network import SubiquityNetworkEventReceiver


class TestRoutes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.er = SubiquityNetworkEventReceiver(Mock())

    def test_empty(self):
        self.assertFalse(self.er._default_route_exists([]))

    def test_one_good(self):
        routes = [
            {
                "target": "localhost",
                "tflags": 0,
                "table": 254,
                "ifname": "ens3",
                "dst": "",
                "dst_len": 0,
                "priority": 100,
                "gateway": "10.0.2.2",
            }
        ]

        self.assertTrue(self.er._default_route_exists(routes))

    def test_mix(self):
        routes = [
            {
                "target": "localhost",
                "tflags": 0,
                "table": 254,
                "ifname": "ens3",
                "dst": "",
                "dst_len": 0,
                "priority": 100,
                "gateway": "10.0.2.2",
            },
            {
                "target": "localhost",
                "tflags": 0,
                "table": 254,
                "ifname": "ens3",
                "dst": "10.0.2.0",
                "dst_len": 24,
                "priority": 100,
                "gateway": None,
            },
            {
                "target": "localhost",
                "tflags": 0,
                "table": 255,
                "ifname": "ens3",
                "dst": "10.0.2.0",
                "dst_len": 24,
                "priority": 100,
                "gateway": None,
            },
            {
                "target": "localhost",
                "tflags": 0,
                "table": 254,
                "ifname": "ens3",
                "dst": "10.0.2.0",
                "dst_len": 24,
                "priority": 20100,
                "gateway": None,
            },
        ]

        self.assertTrue(self.er._default_route_exists(routes))

    def test_one_other(self):
        routes = [
            {
                "target": "localhost",
                "tflags": 0,
                "table": 254,
                "ifname": "ens3",
                "dst": "10.0.2.0",
                "dst_len": 24,
                "priority": 100,
                "gateway": None,
            }
        ]

        self.assertFalse(self.er._default_route_exists(routes))

    def test_wrong_table(self):
        routes = [
            {
                "target": "localhost",
                "tflags": 0,
                "table": 255,
                "ifname": "ens3",
                "dst": "",
                "dst_len": 0,
                "priority": 100,
                "gateway": "10.0.2.2",
            }
        ]

        self.assertFalse(self.er._default_route_exists(routes))

    def test_wrong_priority(self):
        routes = [
            {
                "target": "localhost",
                "tflags": 0,
                "table": 254,
                "ifname": "ens3",
                "dst": "",
                "dst_len": 0,
                "priority": 20100,
                "gateway": "10.0.2.2",
            }
        ]

        self.assertFalse(self.er._default_route_exists(routes))
