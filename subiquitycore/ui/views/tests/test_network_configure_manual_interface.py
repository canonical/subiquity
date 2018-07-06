import unittest
from unittest import mock

import urwid

from subiquitycore.controllers.network import NetworkController
from subiquitycore.models.network import Networkdev, NetworkModel
from subiquitycore.testing import view_helpers
from subiquitycore.ui.views.network_configure_manual_interface import (
    EditNetworkStretchy,
    )
from subiquitycore.view import BaseView


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

        device = mock.create_autospec(spec=Networkdev)
        device.configured_ip_addresses_for_version = lambda v: []
        base_view = BaseView(urwid.Text(""))
        base_view.model = model
        base_view.controller = controller
        base_view.refresh_model_inputs = lambda: None
        stretchy = EditNetworkStretchy(base_view, device, 4)
        base_view.show_stretchy_overlay(stretchy)
        stretchy.method_form.method.value = "manual"
        return base_view, stretchy

    def test_initial_focus(self):
        view, stretchy = self.make_view()
        focus_path = view_helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if w is stretchy.method_form.method.widget:
                return
        else:
            self.fail("method widget not focus")

    def test_done_initially_disabled(self):
        _, stretchy = self.make_view()
        self.assertFalse(stretchy.manual_form.done_btn.enabled)

    def test_done_enabled_for_valid_data(self):
        _, stretchy = self.make_view()
        view_helpers.enter_data(stretchy.manual_form, valid_data)
        self.assertTrue(stretchy.manual_form.done_btn.enabled)

    def test_click_done(self):
        # The ugliness of this test is probably an indication that the
        # view is doing too much...
        view, stretchy = self.make_view()
        view_helpers.enter_data(stretchy.manual_form, valid_data)

        expected = valid_data.copy()
        expected['nameservers'] = [expected['nameservers']]
        expected['searchdomains'] = [expected['searchdomains']]
        expected['network'] = expected.pop('subnet')

        but = view_helpers.find_button_matching(view, "^Save$")
        view_helpers.click(but)

        rinfv = stretchy.device.remove_ip_networks_for_version
        rinfv.assert_called_once_with(4)
        stretchy.device.remove_nameservers.assert_called_once_with()
        stretchy.device.add_network.assert_called_once_with(4, expected)
