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

import unittest
from unittest.mock import Mock

from subiquitycore.controllers.network import (
    BaseNetworkController,
    SubiquityNetworkEventReceiver,
)
from subiquitycore.models.network import NetworkDev, NetworkModel


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


class TestUpdateInitialConfigs(unittest.TestCase):
    def setUp(self):
        self.model = NetworkModel("subiquity")
        self.controller = Mock(model=self.model)

    def add_dev(self, name, typ, config, addresses=()):
        dev = NetworkDev(self.model, name, typ)
        dev.config = config
        dev.info = Mock(
            addresses={a: Mock(scope=scope) for a, scope in addresses},
        )
        self.model.devices_by_name[name] = dev
        return dev

    def cloud_init_config(self, name):
        return {
            "dhcp4": True,
            "match": {"macaddress": "52:54:00:12:34:56"},
            "set-name": name,
        }

    def test_disconnected_nic(self):
        # LP: #2150177 - A NIC that did not get an address must not end up in
        # the configuration of the target system.
        dev = self.add_dev("ens4", "eth", self.cloud_init_config("ens4"))
        BaseNetworkController.update_initial_configs(self.controller)
        self.assertEqual({}, dev.config)
        self.assertIsNotNone(dev.disabled_reason)
        ethernets = self.model.render_config()["network"].get("ethernets", {})
        self.assertNotIn("ens4", ethernets)

    def test_connected_nic(self):
        config = self.cloud_init_config("ens3")
        dev = self.add_dev(
            "ens3", "eth", config.copy(), addresses=[("10.0.2.15/24", "global")]
        )
        BaseNetworkController.update_initial_configs(self.controller)
        self.assertEqual(config, dev.config)
        self.assertIsNone(dev.disabled_reason)

    def test_bond_member(self):
        # Members of a bond have no address but must stay configured.
        dev = self.add_dev("ens4", "eth", self.cloud_init_config("ens4"))
        bond = NetworkDev(self.model, "bond0", "bond")
        bond.config = {"interfaces": ["ens4"], "parameters": {"mode": "802.3ad"}}
        self.model.devices_by_name["bond0"] = bond
        BaseNetworkController.update_initial_configs(self.controller)
        self.assertEqual(
            {"match": {"macaddress": "52:54:00:12:34:56"}, "set-name": "ens4"},
            dev.config,
        )
