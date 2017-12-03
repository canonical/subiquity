import unittest
from unittest import mock

import urwid

from subiquity.controllers.filesystem import FilesystemController
from subiquity.ui.views.filesystem.guided import GuidedFilesystemView

from subiquity.ui.views.tests import helpers


class GuidedFilesystemViewTests(unittest.TestCase):

    def make_view(self):
        controller = mock.create_autospec(spec=FilesystemController)
        return GuidedFilesystemView(controller)

    def test_initial_focus(self):
        view = self.make_view()
        focus_path = helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if isinstance(w, urwid.Button) and w.label == "Use An Entire Disk":
                return
        else:
            self.fail("Guided button not focus")

    def test_click_guided(self):
        view = self.make_view()
        button = helpers.find_button_matching(view, "^Use An Entire Disk$")
        helpers.click(button)
        view.controller.guided.assert_called_once_with()

    def test_click_manual(self):
        view = self.make_view()
        button = helpers.find_button_matching(view, "^Manual$")
        helpers.click(button)
        view.controller.manual.assert_called_once_with()

    def test_click_back(self):
        view = self.make_view()
        button = helpers.find_button_matching(view, "^Back$")
        helpers.click(button)
        view.controller.cancel.assert_called_once_with()
