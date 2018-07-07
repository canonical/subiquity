import unittest
from unittest import mock

import urwid

from subiquitycore.testing import view_helpers

from subiquity.controllers.filesystem import FilesystemController
from subiquity.ui.views.filesystem.guided import GuidedFilesystemView


class GuidedFilesystemViewTests(unittest.TestCase):

    def make_view(self):
        controller = mock.create_autospec(spec=FilesystemController)
        return GuidedFilesystemView(controller)

    def test_initial_focus(self):
        view = self.make_view()
        focus_path = view_helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if isinstance(w, urwid.Button):
                if w.label == "Use An Entire Disk":
                    return
        else:
            self.fail("Guided button not focus")

    def test_click_guided(self):
        view = self.make_view()
        button = (
            view_helpers.find_button_matching(view, "^Use An Entire Disk$"))
        view_helpers.click(button)
        view.controller.guided.assert_called_once_with('direct')

    def test_click_manual(self):
        view = self.make_view()
        button = view_helpers.find_button_matching(view, "^Manual$")
        view_helpers.click(button)
        view.controller.manual.assert_called_once_with()

    def test_click_back(self):
        view = self.make_view()
        button = view_helpers.find_button_matching(view, "^Back$")
        view_helpers.click(button)
        view.controller.cancel.assert_called_once_with()
