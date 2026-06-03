# Copyright 2026 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import unittest
from unittest import mock

import urwid

from subiquity.client.controllers.filesystem import FilesystemController
from subiquity.models.tests.test_filesystem import make_model_and_disk
from subiquity.ui.mount import common_mountpoints, suitable_mountpoints_for_existing_fs
from subiquity.ui.views.filesystem.format import (
    FormatEntireStretchy,
    FormatForm,
)
from subiquitycore.tests.parameterized import parameterized
from subiquitycore.view import BaseView


def make_format_entire_view(model, disk):
    controller = mock.create_autospec(spec=FilesystemController)
    base_view = BaseView(urwid.Text(""))
    base_view.model = model
    base_view.controller = controller
    base_view.refresh_model_inputs = lambda: None
    stretchy = FormatEntireStretchy(base_view, disk)
    base_view.show_stretchy_overlay(stretchy)
    return base_view, stretchy


class TestFormatEntireStretchy(unittest.TestCase):
    def test_format_entire_unusual_filesystem(self):
        model, disk = make_model_and_disk()
        fs = model.add_filesystem(disk, "ntfs")
        fs.preserve = True
        model._orig_config = model._render_actions()
        view, stretchy = make_format_entire_view(model, disk)
        self.assertEqual(stretchy.form.fstype.value, None)


class TestFormatForm(unittest.TestCase):
    def _make_mount_form(
        self,
        mount_value,
        *,
        mountpoints=None,
        existing_fs_type=None,
        fstype_value="ext4",
        remote_storage=False,
    ):
        form = mock.MagicMock(spec=FormatForm)
        form.mount.value = mount_value
        form.mountpoints = mountpoints if mountpoints is not None else {}
        form.existing_fs_type = existing_fs_type
        form.fstype.value = fstype_value
        form.remote_storage = remote_storage
        return form

    def _make_clean_mount_form(self, is_mounted):
        form = mock.MagicMock()
        form.model.is_mounted_filesystem.return_value = is_mounted
        return form

    def test_validate_mount__none(self):
        # None mount value means "leave unmounted"; always accepted.
        form = self._make_mount_form(None)
        self.assertIsNone(FormatForm.validate_mount(form))

    def test_validate_mount__error_path_too_long(self):
        form = self._make_mount_form("a" * 4096)
        self.assertIsNotNone(FormatForm.validate_mount(form))

    def test_validate_mount__error_already_mounted(self):
        form = self._make_mount_form(
            "/home", mountpoints={"/home": mock.sentinel.device}
        )
        with mock.patch(
            "subiquity.ui.views.filesystem.format.labels.label",
            return_value="sda",
        ):
            self.assertIsNotNone(FormatForm.validate_mount(form))

    def test_validate_mount__valid(self):
        form = self._make_mount_form("/home")
        self.assertIsNone(FormatForm.validate_mount(form))

    def test_validate_mount__warning_existing_fs_unsuitable_mountpoint(self):
        # Mounting an existing filesystem at a "bad" common mountpoint shows a
        # warning but is not an error.
        unsuitable = next(
            m
            for m in common_mountpoints
            if m not in suitable_mountpoints_for_existing_fs
        )
        form = self._make_mount_form(
            unsuitable,
            existing_fs_type="ext4",
            fstype_value=None,
        )
        self.assertIsNone(FormatForm.validate_mount(form))
        form.mount.show_extra.assert_called_once()

    def test_validate_mount__no_warning_existing_fs_suitable_mountpoint(self):
        # Mounting an existing filesystem at a suitable mountpoint shows no warning.
        form = self._make_mount_form(
            "/home",
            existing_fs_type="ext4",
            fstype_value=None,
        )
        self.assertIsNone(FormatForm.validate_mount(form))
        form.mount.show_extra.assert_not_called()

    @parameterized.expand([["boot", "/boot"], ["boot_efi", "/boot/efi"]])
    def test_validate_mount__warning_remote_storage(self, _name, mount):
        form = self._make_mount_form(mount, remote_storage=True)
        self.assertIsNone(FormatForm.validate_mount(form))
        form.mount.show_extra.assert_called_once()

    def test_clean_mount__mounted_filesystem_returns_path(self):
        form = self._make_clean_mount_form(is_mounted=True)
        self.assertEqual("/home", FormatForm.clean_mount(form, "/home"))

    def test_clean_mount__unmounted_filesystem_returns_none(self):
        form = self._make_clean_mount_form(is_mounted=False)
        self.assertIsNone(FormatForm.clean_mount(form, "/home"))
