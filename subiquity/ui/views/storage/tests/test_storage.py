import unittest
from unittest import mock

import urwid

from subiquity.client.controllers.storage import StorageController
from subiquity.models.storage import Bootloader, Disk, StorageModel
from subiquity.models.tests.test_storage import FakeStorageInfo, make_model
from subiquity.ui.views.storage.storage import StorageView
from subiquitycore.testing import view_helpers


class StorageViewTests(unittest.TestCase):
    def make_view(self, model, devices=[]):
        controller = mock.create_autospec(spec=StorageController)
        controller.ui = mock.Mock()
        model.bootloader = Bootloader.NONE
        model.all_devices = mock.Mock(return_value=devices)
        return StorageView(model, controller)

    def test_simple(self):
        model = mock.create_autospec(spec=StorageModel)
        model.guidance_messages.return_value = []
        self.make_view(model)

    def test_one_disk(self):
        model = make_model()
        model._probe_data = {}
        model._actions = []
        model._all_ids = set()
        disk = Disk(
            m=model,
            serial="DISK-SERIAL",
            path="/dev/thing",
            info=FakeStorageInfo(size=100 * (2**20), free=50 * (2**20)),
        )
        view = self.make_view(model, [disk])
        w = view_helpers.find_with_pred(
            view, lambda w: isinstance(w, urwid.Text) and "DISK-SERIAL" in w.text
        )
        self.assertIsNotNone(w, "could not find DISK-SERIAL in view")
