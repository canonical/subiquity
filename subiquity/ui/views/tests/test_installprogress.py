import unittest
from unittest import mock
from unittest.mock import patch

from subiquity.client.controllers.progress import ProgressController
from subiquity.common.types import ApplicationState
from subiquity.ui.views.installprogress import ProgressView
from subiquitycore.testing import view_helpers


class IdentityViewTests(unittest.TestCase):
    def make_view(self):
        controller = mock.create_autospec(spec=ProgressController)
        controller.app = mock.Mock()
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
        view.update_for_state(ApplicationState.DONE)
        btn = view_helpers.find_button_matching(view, "^Reboot Now$")
        self.assertIsNot(btn, None)
        view_helpers.click(btn)
        view.controller.click_reboot.assert_called_once_with()

    def test_error_disambiguation(self):
        view = self.make_view()

        # Reportable errors
        view.controller.has_nonreportable_error = False
        view.update_for_state(ApplicationState.ERROR)
        btn = view_helpers.find_button_matching(view, "^View error report$")
        self.assertIsNotNone(btn)
        btn = view_helpers.find_button_matching(view, "^Reboot Now$")
        self.assertIsNotNone(btn)
        btn = view_helpers.find_button_matching(view, "^Restart Installer$")
        self.assertIsNone(btn)

        # Non-Reportable errors
        view.controller.has_nonreportable_error = True
        view.update_for_state(ApplicationState.ERROR)
        btn = view_helpers.find_button_matching(view, "^View error report$")
        self.assertIsNone(btn)
        btn = view_helpers.find_button_matching(view, "^Reboot Now$")
        self.assertIsNone(btn)
        btn = view_helpers.find_button_matching(view, "^Restart Installer$")
        self.assertIsNotNone(btn)

    @patch("subiquity.ui.views.installprogress.Columns")
    @patch("subiquity.ui.views.installprogress.Text")
    def test_event_other_formatting(self, text_mock, columns_mock):
        """Test formatting of the other_event function."""
        view = self.make_view()
        text_mock.return_value = "mock text"
        view.event_other("MOCK CONTEXT: message", "mock")
        text_mock.assert_called_with("MOCK CONTEXT: MOCK: message")
        columns_mock.assert_called_with(
            [
                ("pack", "mock text"),
            ],
            dividechars=1,
        )

    @patch("subiquity.ui.views.installprogress.Text")
    def test_event_other_robust_splitting(self, text_mock):
        """Test that messages containing a colon don't fail to split.

        event_other uses str.split(":"), make sure it doesn't cause an
        error if more than one colon is present in the message.
        """
        view = self.make_view()
        view.event_other("MOCK CONTEXT: bad keys: 1, 2, 3", "mock")
        text_mock.assert_called_with("MOCK CONTEXT: MOCK: bad keys: 1, 2, 3")
