import unittest
from unittest import mock

import urwid

from probert.storage import StorageInfo

from subiquitycore.testing import view_helpers

from subiquity.controllers.filesystem import FilesystemController
from subiquity.models.filesystem import (
    Disk,
    FilesystemModel,
    Partition,
    )
from subiquity.ui.views.filesystem.partition import PartitionView



class PartitionViewTests(unittest.TestCase):

    def make_view(self, partition=None):
        controller = mock.create_autospec(spec=FilesystemController)
        model = mock.create_autospec(spec=FilesystemModel)
        model.fs_by_name = FilesystemModel.fs_by_name
        info = mock.create_autospec(spec=StorageInfo)
        info.name = 'disk-name'
        info.size = 100
        info.free = 50
        disk = Disk.from_info(info)
        return PartitionView(model, controller, disk, partition)

    def test_initial_focus(self):
        view = self.make_view()
        focus_path = view_helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if w is view.form.partnum.widget:
                return
        else:
            self.fail("Guided button not focus")

    def test_no_delete_for_new_partition(self):
        view = self.make_view()
        self.assertIsNone(view_helpers.find_button_matching(view, "Delete"))

    def test_delete_present_for_partition(self):
        view = self.make_view(Partition(size=50))
        self.assertIsNotNone(view_helpers.find_button_matching(view, "Delete"))
