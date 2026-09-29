# Copyright 2023 Canonical, Ltd.
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

import copy
import unittest
from unittest.mock import Mock

from subiquitycore.controllers.network import (
    BaseNetworkController,
    SubiquityNetworkEventReceiver,
)
from subiquitycore.models.network import NetworkDev, StaticConfig


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


class TestSetStaticConfig(unittest.TestCase):
    def setUp(self):
        model = Mock(get_all_netdevs=Mock(return_value=[]))
        self.dev = NetworkDev(model, "eth0", "eth")
        self.controller = Mock()
        self.controller.model.get_netdev_by_name.return_value = self.dev

    def set_static_config(self, ip_version, **kwargs):
        BaseNetworkController.set_static_config(
            self.controller, "eth0", ip_version, StaticConfig(**kwargs)
        )

    def test_edit_round_trip(self):
        # LP: #2041828 - saving the configuration shown when editing an
        # interface should not lose the gateway nor the name servers.
        config = StaticConfig(
            addresses=["10.0.1.15/24"],
            gateway="10.0.1.1",
            nameservers=["10.0.1.2"],
            searchdomains=["example.com"],
        )
        BaseNetworkController.set_static_config(self.controller, "eth0", 4, config)
        self.assertEqual(config, self.dev.netdev_info().static4)

        expected = copy.deepcopy(self.dev.config)
        BaseNetworkController.set_static_config(
            self.controller, "eth0", 4, self.dev.netdev_info().static4
        )
        self.assertEqual(expected, self.dev.config)

    def test_keep_default_route_of_other_ip_version(self):
        # LP: #1993792
        self.set_static_config(4, addresses=["10.0.1.15/24"], gateway="10.0.1.1")
        self.set_static_config(6, addresses=["fd00::15/64"], gateway="fd00::1")
        self.assertCountEqual(
            [
                {"to": "default", "via": "10.0.1.1"},
                {"to": "default", "via": "fd00::1"},
            ],
            self.dev.config["routes"],
        )

        self.set_static_config(4, addresses=["10.0.1.15/24"], gateway="10.0.1.254")
        self.assertCountEqual(
            [
                {"to": "default", "via": "10.0.1.254"},
                {"to": "default", "via": "fd00::1"},
            ],
            self.dev.config["routes"],
        )

    def test_remove_gateway(self):
        self.set_static_config(4, addresses=["10.0.1.15/24"], gateway="10.0.1.1")
        self.set_static_config(6, addresses=["fd00::15/64"], gateway="fd00::1")
        self.set_static_config(4, addresses=["10.0.1.15/24"])
        self.assertEqual(
            [{"to": "default", "via": "fd00::1"}], self.dev.config["routes"]
        )
