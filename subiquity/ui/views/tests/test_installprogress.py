import unittest
from unittest import mock

from subiquitycore.testing import view_helpers

from subiquity.client.controllers.progress import ProgressController
from subiquity.common.types import InstallState
from subiquity.ui.views.installprogress import ProgressView


class IdentityViewTests(unittest.TestCase):

    def make_view(self):
        controller = mock.create_autospec(spec=ProgressController)
        controller.app = mock.Mock()
        controller.app.aio_loop = None
        return ProgressView(controller)

    def test_initial_focus(self):
        view = self.make_view()
        for w in reversed(view_helpers.get_focus_path(view)):
            if w is view.event_listbox:
                return
        else:
            self.fail("event listbox widget not focus")

    def test_show_complete(self):
        view = self.make_view()
        btn = view_helpers.find_button_matching(view, "^Reboot Now$")
        self.assertIs(btn, None)
        view.update_for_state(InstallState.DONE)
        btn = view_helpers.find_button_matching(view, "^Reboot Now$")
        self.assertIsNot(btn, None)
        view_helpers.click(btn)
        view.controller.click_reboot.assert_called_once_with()
