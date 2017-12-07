import unittest
from unittest import mock


from subiquitycore.controllers.network import NetworkController
from subiquitycore.models.network import Networkdev, NetworkModel
from subiquitycore.testing import view_helpers
from subiquitycore.ui.views.network_configure_manual_interface import NetworkConfigureIPv4InterfaceView


class TestNetworkConfigureIPv4InterfaceView(unittest.TestCase):

    def make_view(self):
        model = mock.create_autospec(spec=NetworkModel)
        controller = mock.create_autospec(spec=NetworkController)
        ifname = 'ifname'
        def get_netdev_by_name(name):
            if name == ifname:
                # The view does not access any of the current state of
                # the device so passing None for the probert data
                # works. This is a bit sketchy but oh well!
                return Networkdev(None, {})
            else:
                raise AssertionError("get_netdev_by_name called with unexpected arg %s"%(name,))
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
