import enum
import typing
import unittest
from unittest import mock

import attr

import urwid

from subiquitycore.controllers.network import NetworkController
from subiquitycore.models.network import NetDevInfo, StaticConfig
from subiquitycore.testing import view_helpers
from subiquitycore.ui.views.network_configure_manual_interface import (
    EditNetworkStretchy,
    ViewInterfaceInfo,
    )
from subiquitycore.view import BaseView


valid_data = {
    'subnet': '10.0.2.0/24',
    'address': '10.0.2.15',
    'gateway': '10.0.2.2',
    'nameservers': '8.8.8.8',
    'searchdomains': '.custom',
    }


def create_test_instance(cls, name=(), *, overrides={}):
    if '.'.join(name) in overrides:
        return overrides['.'.join(name)]
    if attr.has(cls):
        args = {}
        for field in attr.fields(cls):
            args[field.name] = create_test_instance(
                field.type, name + (field.name,), overrides=overrides)
        return cls(**args)
    elif hasattr(cls, '__origin__'):
        t = cls.__origin__
        if t is typing.Union and type(None) in cls.__args__:
            return None
        elif t in [list, typing.List]:
            return [
                create_test_instance(
                    cls.__args__[0], name, overrides=overrides),
                ]
        else:
            raise Exception(
                "do not understand annotation {} at {}".format(
                    t, '.'.join(name)))
    elif issubclass(cls, enum.Enum):
        return next(iter(cls))
    else:
        try:
            return cls()
        except Exception:
            raise Exception("instantiating {} failed".format(cls))


class TestNetworkConfigureIPv4InterfaceView(unittest.TestCase):

    def make_view(self, dev_info=None):
        if dev_info is None:
            dev_info = create_test_instance(
                NetDevInfo, overrides={'static4.addresses': ['1.2.3.4/5']})
        base_view = BaseView(urwid.Text(""))
        base_view.update_link = lambda device: None
        base_view.controller = mock.create_autospec(spec=NetworkController)
        stretchy = EditNetworkStretchy(base_view, dev_info, 4)
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
        dev_info = create_test_instance(
            NetDevInfo, overrides={'static4.addresses': []})
        _, stretchy = self.make_view(dev_info)
        self.assertFalse(stretchy.manual_form.done_btn.enabled)

    def test_done_enabled_for_valid_data(self):
        valid_data = {
            'subnet': '10.0.2.0/24',
            'address': '10.0.2.15',
            }
        _, stretchy = self.make_view()
        view_helpers.enter_data(stretchy.manual_form, valid_data)
        self.assertTrue(stretchy.manual_form.done_btn.enabled)

    def test_click_done(self):
        # The ugliness of this test is probably an indication that the
        # view is doing too much...
        dev_info = create_test_instance(
            NetDevInfo, overrides={'static4.addresses': []})
        view, stretchy = self.make_view(dev_info)
        valid_data = {
            'subnet': '10.0.2.0/24',
            'address': '10.0.2.15',
            'gateway': '10.0.2.2',
            'nameservers': '8.8.8.8, 1.1.1.1',
            'searchdomains': '.custom, .zzz',
            }
        view_helpers.enter_data(stretchy.manual_form, valid_data)

        expected = StaticConfig(
            addresses=['10.0.2.15/24'],
            gateway='10.0.2.2',
            nameservers=['8.8.8.8', '1.1.1.1'],
            searchdomains=['.custom', '.zzz'])

        but = view_helpers.find_button_matching(view, "^Save$")
        view_helpers.click(but)

        view.controller.set_static_config.assert_called_once_with(
            stretchy.dev_info.name, 4, expected)


class FakeLink:
    def serialize(self):
        return "INFO"


class TestViewInterfaceInfo(unittest.TestCase):

    def make_view(self, *, info):
        dev_info = create_test_instance(NetDevInfo)
        base_view = BaseView(urwid.Text(""))
        base_view.controller = mock.Mock()
        base_view.controller.get_info_for_netdev.return_value = "INFO"
        stretchy = ViewInterfaceInfo(base_view, dev_info)
        base_view.show_stretchy_overlay(stretchy)
        return base_view, stretchy

    def test_view(self):
        view, stretchy = self.make_view(info=FakeLink())
        text = view_helpers.find_with_pred(
            view, lambda w: isinstance(w, urwid.Text) and "INFO" in w.text)
        self.assertNotEqual(text, None)
