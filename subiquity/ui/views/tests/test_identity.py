import unittest
from unittest import mock

from subiquitycore.models.identity import IdentityModel
from subiquitycore.signals import Signal

from subiquity.controllers.identity import IdentityController
from subiquity.ui.views.identity import IdentityView

from subiquity.ui.views.tests import helpers


class IdentityViewTests(unittest.TestCase):

    def make_view(self):
        model = mock.create_autospec(spec=IdentityModel)
        controller = mock.create_autospec(spec=IdentityController)
        controller.signal = mock.create_autospec(spec=Signal)
        return IdentityView(model, controller, {})

    def enter_valid_data(self, view):
        view.form.realname.value = view.form.hostname.value = view.form.username.value = view.form.password.value = view.form.confirm_password.value = 'w'

    def test_done_initially_disabled(self):
        view = self.make_view()
        self.assertFalse(view.form.done_btn.enabled)

    def test_initial_focus(self):
        view = self.make_view()
        focus_path = helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if w is view.form.realname.widget:
                return
        else:
            self.fail("Realname widget not focus")

    def test_can_tab_to_done_when_valid(self):
        view = self.make_view()
        self.enter_valid_data(view)
        self.assertTrue(view.form.done_btn.enabled)
        for i in range(10):
            helpers.keypress(view, 'tab', size=(80, 24))
            focus_path = helpers.get_focus_path(view)
            for w in reversed(focus_path):
                if w is view.form.done_btn:
                    return
        self.fail("could not tab to done button")
