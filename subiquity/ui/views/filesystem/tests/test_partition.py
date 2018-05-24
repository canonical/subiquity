import unittest
from unittest import mock

import urwid

from probert.storage import StorageInfo

from subiquitycore.testing import view_helpers

from subiquity.controllers.filesystem import FilesystemController
from subiquity.models.filesystem import (
    dehumanize_size,
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
        info.size = 100*(2**20)
        info.free = 50*(2**20)
        disk = Disk.from_info(info)
        return PartitionView(model, controller, disk, partition)

    def test_initial_focus(self):
        view = self.make_view()
        focus_path = view_helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if w is view.form.size.widget:
                return
        else:
            self.fail("Guided button not focus")

    def test_no_delete_for_new_partition(self):
        view = self.make_view()
        self.assertIsNone(view_helpers.find_button_matching(view, "Delete"))

    def test_delete_not_disabled_for_ordinary_partition(self):
        view = self.make_view(Partition(size=50*(2**20)))
        but, path = view_helpers.find_button_matching(view, "Delete",
                                                      return_path=True)
        self.assertIsNotNone(but)
        for w in path:
            if isinstance(w, urwid.WidgetDisable):
                self.fail("Delete button is disabled")

    def test_delete_disabled_for_boot_partition(self):
        view = self.make_view(Partition(size=50*(2**20), flag="boot"))
        but, path = view_helpers.find_button_matching(view, "Delete",
                                                      return_path=True)
        self.assertIsNotNone(but)
        for w in path:
            if isinstance(w, urwid.WidgetDisable):
                return
        else:
            self.fail("Delete button not disabled")

    def test_click_delete_button(self):
        partition = Partition(size=50*(2**20))
        view = self.make_view(partition)
        but = view_helpers.find_button_matching(view, "Delete")
        view_helpers.click(but)
        view.controller.delete_partition.assert_called_once_with(partition)

    def test_create_partition(self):
        valid_data = {
            'size': "1M",
            'fstype': FilesystemModel.fs_by_name["ext4"],
            }
        view = self.make_view()
        view_helpers.enter_data(view.form, valid_data)
        view_helpers.click(view.form.done_btn.base_widget)
        valid_data['mount'] = '/'
        valid_data['size'] = dehumanize_size(valid_data['size'])
        view.controller.partition_disk_handler.assert_called_once_with(
            view.disk, None, valid_data)
