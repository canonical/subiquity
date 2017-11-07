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
