import unittest
from unittest import mock


from subiquitycore.controllers.network import NetworkController
from subiquitycore.models.network import Networkdev, NetworkModel
from subiquitycore.testing import view_helpers
from subiquitycore.ui.views.network_configure_manual_interface import (
    NetworkConfigureIPv4InterfaceView)


valid_data = {
    'subnet': '10.0.2.0/24',
    'address': '10.0.2.15',
    'gateway': '10.0.2.2',
    'nameservers': '8.8.8.8',
    'searchdomains': '.custom',
    }


class TestNetworkConfigureIPv4InterfaceView(unittest.TestCase):

    def make_view(self):
        model = mock.create_autospec(spec=NetworkModel)
        controller = mock.create_autospec(spec=NetworkController)
        ifname = 'ifname'

        def get_netdev_by_name(name):
            if name == ifname:
                dev = mock.create_autospec(spec=Networkdev)
                dev.configured_ip_addresses_for_version = lambda v: []
                return dev
            else:
                raise AssertionError("get_netdev_by_name called with "
                                     "unexpected arg %s" % (name,))
        model.get_netdev_by_name.side_effect = get_netdev_by_name
        return NetworkConfigureIPv4InterfaceView(model, controller, ifname)

    def test_initial_focus(self):
        view = self.make_view()
        focus_path = view_helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if w is view.form.subnet.widget:
                return
        else:
            self.fail("Subnet widget not focus")

    def test_done_initially_disabled(self):
        view = self.make_view()
        self.assertFalse(view.form.done_btn.enabled)

    def test_done_enabled_for_valid_data(self):
        view = self.make_view()
        view_helpers.enter_data(view.form, valid_data)
        self.assertTrue(view.form.done_btn.enabled)

    def test_click_done(self):
        # The ugliness of this test is probably an indication that the
        # view is doing too much...
        view = self.make_view()
        view_helpers.enter_data(view.form, valid_data)

        expected = valid_data.copy()
        expected['nameservers'] = [expected['nameservers']]
        expected['searchdomains'] = [expected['searchdomains']]
        expected['network'] = expected.pop('subnet')

        but = view_helpers.find_button_matching(view, "^Save$")
        view_helpers.click(but)

        view.dev.remove_ip_networks_for_version.assert_called_once_with(4)
        view.dev.remove_nameservers.assert_called_once_with()
        view.dev.add_network.assert_called_once_with(4, expected)
