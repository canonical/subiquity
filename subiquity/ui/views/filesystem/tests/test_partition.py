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

    def make_model_and_disk(self):
        model = FilesystemModel(prober=None)
        disk = Disk.from_info(FakeStorageInfo(
            name='disk-name', size=100*(2**30), free=50*(2**30)))
        model._available_disks[disk.name] = disk
        return model, disk

    def make_view(self, model, disk, partition=None):
        controller = mock.create_autospec(spec=FilesystemController)
        base_view = BaseView(urwid.Text(""))
        base_view.model = model
        base_view.controller = controller
        base_view.refresh_model_inputs = lambda: None
        stretchy = PartitionStretchy(base_view, disk, partition)
        base_view.show_stretchy_overlay(stretchy)
        return base_view, stretchy

    def test_initial_focus(self):
        model, disk = self.make_model_and_disk()
        view, stretchy = self.make_view(model, disk)
        focus_path = view_helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if w is stretchy.form.size.widget:
                return
        else:
            self.fail("Size widget not focus")

    def test_create_partition(self):
        valid_data = {
            'size': "1M",
            'fstype': FilesystemModel.fs_by_name["ext4"],
            }
        model, disk = self.make_model_and_disk()
        view, stretchy = self.make_view(model, disk)
        view_helpers.enter_data(stretchy.form, valid_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        valid_data['mount'] = '/'
        valid_data['size'] = dehumanize_size(valid_data['size'])
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, None, valid_data)

    def test_edit_partition(self):
        form_data = {
            'size': "256M",
            'fstype': FilesystemModel.fs_by_name['xfs'],
            }
        model, disk = self.make_model_and_disk()
        partition = model.add_partition(disk, 512*(2**20))
        model.add_filesystem(partition, "ext4")
        view, stretchy = self.make_view(model, disk, partition)
        self.assertTrue(stretchy.form.done_btn.enabled)
        view_helpers.enter_data(stretchy.form, form_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            'size': dehumanize_size(form_data['size']),
            'fstype': FilesystemModel.fs_by_name['xfs'],
            'mount': None,
            }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, stretchy.partition, expected_data)

    def test_edit_boot_partition(self):
        form_data = {
            'size': "256M",
            }
        model, disk = self.make_model_and_disk()
        partition = model.add_partition(disk, 512*(2**20), "boot")
        fs = model.add_filesystem(partition, "fat32")
        model.add_mount(fs, '/boot/efi')
        view, stretchy = self.make_view(model, disk, partition)
        view_helpers.enter_data(stretchy.form, form_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            'size': dehumanize_size(form_data['size']),
            'fstype': FilesystemModel.fs_by_name["fat32"],
            'mount': '/boot/efi',
            }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, stretchy.partition, expected_data)
