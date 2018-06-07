import unittest
from unittest import mock
from collections import namedtuple

import urwid

from subiquitycore.testing import view_helpers

from subiquity.controllers.filesystem import FilesystemController
from subiquity.models.filesystem import (
    Disk,
    FilesystemModel,
    )
from subiquity.ui.views.filesystem.filesystem import FilesystemView


FakeStorageInfo = namedtuple(
    'FakeStorageInfo', ['name', 'size', 'free', 'serial', 'model'])
FakeStorageInfo.__new__.__defaults__ = (None,) * len(FakeStorageInfo._fields)


class FilesystemViewTests(unittest.TestCase):

    def make_view(self, devices=[]):
        controller = mock.create_autospec(spec=FilesystemController)
        model = mock.create_autospec(spec=FilesystemModel)
        model.all_devices.return_value = devices
        return FilesystemView(model, controller)

    def test_simple(self):
        self.make_view()

    def test_one_disk(self):
        disk = Disk.from_info(FakeStorageInfo(
            name='disk-name', size=100*(2**20), free=50*(2**20), serial="DISK-SERIAL"))
        view = self.make_view([disk])
        def pred(w):
            return isinstance(w, urwid.Text) and "DISK-SERIAL" in w.text
        w = view_helpers.find_with_pred(view, pred)
        self.assertIsNotNone(w, "could not find DISK-SERIAL in view")
