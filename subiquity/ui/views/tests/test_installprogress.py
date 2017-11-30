import unittest
from unittest import mock


from subiquity.controllers.installprogress import InstallProgressController
from subiquity.ui.views.installprogress import ProgressView

from subiquity.ui.views.tests import helpers


class IdentityViewTests(unittest.TestCase):

    def make_view(self):
        controller = mock.create_autospec(spec=InstallProgressController)
        return ProgressView(controller)

    def test_initial_focus(self):
        view = self.make_view()
        for w in reversed(helpers.get_focus_path(view)):
            if w is view.listbox:
                return
        else:
            self.fail("listbox widget not focus")

    def test_show_complete(self):
        view = self.make_view()
        btn = helpers.find_button_matching(view, "^Reboot Now$")
        self.assertIs(btn, None)
        view.show_complete()
        btn = helpers.find_button_matching(view, "^Reboot Now$")
        self.assertIsNot(btn, None)
        helpers.click(btn)
        view.controller.reboot.assert_called_once_with()
