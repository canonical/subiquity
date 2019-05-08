import unittest
from unittest import mock
from collections import namedtuple

import urwid

from subiquitycore.testing import view_helpers

from subiquity.controllers.filesystem import FilesystemController
from subiquity.models.filesystem import (
    Bootloader,
    Disk,
    FilesystemModel,
    )
from subiquity.ui.views.filesystem.filesystem import FilesystemView


FakeStorageInfo = namedtuple(
    'FakeStorageInfo', ['name', 'size', 'free', 'serial', 'model'])
FakeStorageInfo.__new__.__defaults__ = (None,) * len(FakeStorageInfo._fields)


class FilesystemViewTests(unittest.TestCase):

    def make_view(self, model, devices=[]):
        controller = mock.create_autospec(spec=FilesystemController)
        controller.ui = mock.Mock()
        model.bootloader = Bootloader.NONE
        model.all_devices.return_value = devices
        model.grub_install_device = None
        return FilesystemView(model, controller)

    def test_simple(self):
        self.make_view(mock.create_autospec(spec=FilesystemModel))

    def test_one_disk(self):
        model = mock.create_autospec(spec=FilesystemModel)
        disk = Disk.from_info(model, FakeStorageInfo(
            name='disk-name', size=100*(2**20), free=50*(2**20),
            serial="DISK-SERIAL"))
        view = self.make_view(model, [disk])
        w = view_helpers.find_with_pred(
            view,
            lambda w: isinstance(w, urwid.Text) and "DISK-SERIAL" in w.text)
        self.assertIsNotNone(w, "could not find DISK-SERIAL in view")
