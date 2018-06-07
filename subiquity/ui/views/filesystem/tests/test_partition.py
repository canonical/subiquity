import unittest
from unittest import mock
from collections import namedtuple

import urwid

from subiquitycore.testing import view_helpers
from subiquitycore.view import BaseView

from subiquity.controllers.filesystem import FilesystemController
from subiquity.models.filesystem import (
    dehumanize_size,
    Disk,
    FilesystemModel,
    Partition,
    )
from subiquity.ui.views.filesystem.partition import PartitionStretchy


FakeStorageInfo = namedtuple(
    'FakeStorageInfo', ['name', 'size', 'free', 'serial', 'model'])
FakeStorageInfo.__new__.__defaults__ = (None,) * len(FakeStorageInfo._fields)


class PartitionViewTests(unittest.TestCase):

    def make_view(self, partition=None):
        controller = mock.create_autospec(spec=FilesystemController)
        model = mock.create_autospec(spec=FilesystemModel)
        model.fs_by_name = FilesystemModel.fs_by_name
        disk = Disk.from_info(FakeStorageInfo(
            name='disk-name', size=100*(2**20), free=50*(2**20)))
        base_view = BaseView(urwid.Text(""))
        base_view.model = model
        base_view.controller = controller
        base_view.refresh_model_inputs = lambda:None
        stretchy = PartitionStretchy(base_view, disk, partition)
        base_view.show_stretchy_overlay(stretchy)
        return base_view, stretchy

    def test_initial_focus(self):
        view, stretchy = self.make_view()
        focus_path = view_helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if w is stretchy.form.size.widget:
                return
        else:
            self.fail("Guided button not focus")

    def test_create_partition(self):
        valid_data = {
            'size': "1M",
            'fstype': FilesystemModel.fs_by_name["ext4"],
            }
        view, stretchy = self.make_view()
        view_helpers.enter_data(stretchy.form, valid_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        valid_data['mount'] = '/'
        valid_data['size'] = dehumanize_size(valid_data['size'])
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, None, valid_data)
