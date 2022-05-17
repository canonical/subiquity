import asyncio
import unittest
from unittest import mock

from subiquitycore.testing import view_helpers

from subiquity.client.controllers.identity import IdentityController
from subiquity.common.types import IdentityData, UsernameValidation
from subiquity.ui.views.identity import IdentityView


valid_data = {
    'realname': 'Real Name',
    'hostname': 'host-name',
    'username': 'username',
    'password': 'password',
    'confirm_password': 'password'
    }

too_long = {
    'realname': 'Real Name',
    'hostname': 'host-name',
    'username': 'u'*33,
    'password': 'password',
    'confirm_password': 'password'
    }

already_taken = {
    'realname': 'Real Name',
    'hostname': 'host-name',
    'username': 'root',
    'password': 'password',
    'confirm_password': 'password'
    }

system_reserved = {
    'realname': 'Real Name',
    'hostname': 'host-name',
    'username': 'plugdev',
    'password': 'password',
    'confirm_password': 'password'
    }


def tearDownModule() -> None:
    # Set empty loop policy, so that subsequent get_event_loop() returns a new
    # loop. If there is no running event loop set, that function will return
    # the result of `get_event_loop_policy().get_event_loop()` call. If there
    # is a policy there must be a running loop. IsolatedAsyncioTestCase
    # closes the loop during tear down, though. It doesn't touch the policy.
    # By having it as None, it autoinits and the next tests run smoothly.
    # Another approach would be set a new event_loop for the current policy on
    # test fixture tearDown, as pytest-ayncio does.
    # Either way we would prevent failure on tests that depend on [run_coro]
    # (subiquitycore/tests/util.py), for instance.
    asyncio.set_event_loop_policy(None)


class IdentityViewTests(unittest.IsolatedAsyncioTestCase):

    def make_view(self):
        controller = mock.create_autospec(spec=IdentityController)
        return IdentityView(controller, IdentityData())

    def test_initial_focus(self):
        view = self.make_view()
        focus_path = view_helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if w is view.form.realname.widget:
                return
        else:
            self.fail("Realname widget not focus")

    def test_done_initially_disabled(self):
        view = self.make_view()
        self.assertFalse(view.form.done_btn.enabled)

    def test_done_enabled_when_valid(self):
        view = self.make_view()
        view_helpers.enter_data(view.form, valid_data)
        self.assertTrue(view.form.done_btn.enabled)

    async def test_username_validation_system_reserved(self):
        view = self.make_view()
        widget = view.form.username.widget
        view.controller.validate_username.return_value = \
            UsernameValidation.SYSTEM_RESERVED
        view_helpers.enter_data(view.form, system_reserved)
        widget.lost_focus()
        await widget.validation_task
        self.assertFalse(view.form.done_btn.enabled)

    async def test_username_validation_in_use(self):
        view = self.make_view()
        widget = view.form.username.widget
        view.controller.validate_username.return_value = \
            UsernameValidation.ALREADY_IN_USE
        view_helpers.enter_data(view.form, already_taken)
        widget.lost_focus()
        await widget.validation_task
        self.assertFalse(view.form.done_btn.enabled)

    def test_username_validation_too_long(self):
        view = self.make_view()
        view_helpers.enter_data(view.form, too_long)
        self.assertFalse(view.form.done_btn.enabled)

    def test_click_done(self):
        view = self.make_view()
        CRYPTED = '<crypted>'
        with mock.patch('subiquity.ui.views.identity.crypt_password') as cp:
            cp.side_effect = lambda p: CRYPTED
            view_helpers.enter_data(view.form, valid_data)
            done_btn = view_helpers.find_button_matching(view, "^Done$")
            view_helpers.click(done_btn)
        expected = IdentityData(
            realname=valid_data['realname'],
            username=valid_data['username'],
            hostname=valid_data['hostname'],
            crypted_password=CRYPTED)
        view.controller.done.assert_called_once_with(expected)

    def test_can_tab_to_done_when_valid(self):
        # Urwid doesn't distinguish very well between widgets that are
        # not currently selectable and widgets that can never be
        # selectable. The "button pile" of the identity view is
        # initially not selectable but becomes selectable when valid
        # data is entered. This test checks that urwid notices this :)
        # by simulating lots of presses of the tab key and checking if
        # the done button has been focused.
        view = self.make_view()
        view_helpers.enter_data(view.form, valid_data)

        for i in range(100):
            view_helpers.keypress(view, 'tab', size=(80, 24))
            focus_path = view_helpers.get_focus_path(view)
            for w in reversed(focus_path):
                if w is view.form.done_btn:
                    return
        self.fail("could not tab to done button")
