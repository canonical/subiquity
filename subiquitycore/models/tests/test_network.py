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

from unittest.mock import Mock

from subiquitycore.models.network import BondConfig, BondParameters, NetworkDev
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.parameterized import parameterized


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


class TestNetworkDev(SubiTestCase):
    def setUp(self):
        self.model = Mock(get_all_netdevs=Mock(return_value=[]))

    def test_netdev_info_eth_inexistent(self):
        # LP: #2012659 - just after physically removing an Ethernet interface
        # from the system, Subiquity tries to collect information via
        # netdev_info. The code would try to dereference dev.info - but it was
        # reset to None when the interface got removed.
        # In other private reports, the same issue would occur with Wi-Fi
        # interfaces.
        nd = NetworkDev(self.model, "testdev0", "eth")
        info = nd.netdev_info()
        self.assertFalse(info.is_connected)

    def test_netdev_info_wlan_inexistent(self):
        # Just like test_netdev_info_eth_inexistent but with Wi-Fi interfaces
        # which suffer the same issue.
        nd = NetworkDev(self.model, "testdev0", "wlan")
        info = nd.netdev_info()
        self.assertIsNone(info.wlan.scan_state)
        self.assertEqual(info.wlan.visible_ssids, [])

    def test_netdev_info_bond_extract(self):
        nd = NetworkDev(self.model, "testdev0", "bond")
        bond = BondConfig(["interface"], "802.3ad", "layer3+4", "slow")
        nd.config = bond.to_config()
        info = nd.netdev_info()
        self.assertEqual(info.bond, bond)

    def test_remove_ip_network__no_nameserver(self):
        """Test remove nameservers when no static addresses remain."""
        nd = NetworkDev(self.model, "testdev0", "eth")
        nd.config = {
            "addresses": ["10.0.1.15/24", "f:db28::/32"],
            "nameservers": {
                "addresses": ["8.8.8.8", "8.4.8.4"],
                "search": ["foo", "bar"],
            },
            "routes": [{"to": "default", "via": "10.0.2.2"}],
        }
        nd.remove_ip_networks_for_version(4)
        self.assertIn("nameservers", nd.config)

        nd.remove_ip_networks_for_version(6)
        self.assertNotIn("nameservers", nd.config)

    def test_remove_ip_network__config_empty(self):
        """Test that removing ipv4 and ipv6 networks causes the config to be empty."""
        net_dev = NetworkDev(self.model, "testdev0", "eth")
        net_dev.config = {
            "dhcp6": True,
            "addresses": ["10.0.1.15/24"],
            "nameservers": {
                "addresses": ["8.8.8.8", "8.4.8.4"],
                "search": ["foo", "bar"],
            },
            "routes": [{"to": "default", "via": "10.0.2.2"}],
        }
        net_dev.remove_ip_networks_for_version(4)
        net_dev.remove_ip_networks_for_version(6)
        self.assertEqual(net_dev.config, {})


class TestBondConfig(SubiTestCase):
    @parameterized.expand(
        [
            (mode, ["interface"], mode, "transmit", "lacp")
            for mode in BondParameters.modes
        ]
    )
    def test_to_config(self, name, interfaces, mode, transmit, lacp):
        bond = BondConfig(interfaces, mode, transmit, lacp)
        config = bond.to_config()
        params = config["parameters"]
        self.assertEqual(config["interfaces"], interfaces)
        self.assertEqual(params["mode"], mode)
        if mode in BondParameters.supports_xmit_hash_policy:
            self.assertIn(
                "transmit-hash-policy", params
            )  # redundant but helpful error message
            self.assertEqual(params["transmit-hash-policy"], transmit)
        else:
            self.assertNotIn("transmit-hash-policy", params)
        if mode in BondParameters.supports_lacp_rate:
            self.assertIn("lacp-rate", params)  # redundant but helpful error message
            self.assertEqual(params["lacp-rate"], lacp)
        else:
            self.assertNotIn("lacp-rate", params)
