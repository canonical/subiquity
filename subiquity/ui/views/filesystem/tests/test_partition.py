import unittest
from unittest import mock

import urwid

from subiquitycore.testing import view_helpers
from subiquitycore.view import BaseView

from subiquity.client.controllers.filesystem import FilesystemController
from subiquity.models.filesystem import (
    dehumanize_size,
    )
from subiquity.models.tests.test_filesystem import (
    make_model_and_disk,
    )
from subiquity.ui.views.filesystem.partition import (
    FormatEntireStretchy,
    PartitionStretchy,
    )


def make_partition_view(model, disk, partition=None):
    controller = mock.create_autospec(spec=FilesystemController)
    base_view = BaseView(urwid.Text(""))
    base_view.model = model
    base_view.controller = controller
    base_view.refresh_model_inputs = lambda: None
    stretchy = PartitionStretchy(base_view, disk, partition)
    base_view.show_stretchy_overlay(stretchy)
    return base_view, stretchy


def make_format_entire_view(model, disk):
    controller = mock.create_autospec(spec=FilesystemController)
    base_view = BaseView(urwid.Text(""))
    base_view.model = model
    base_view.controller = controller
    base_view.refresh_model_inputs = lambda: None
    stretchy = FormatEntireStretchy(base_view, disk)
    base_view.show_stretchy_overlay(stretchy)
    return base_view, stretchy


class PartitionViewTests(unittest.TestCase):

    def test_initial_focus(self):
        model, disk = make_model_and_disk()
        view, stretchy = make_partition_view(model, disk)
        focus_path = view_helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if w is stretchy.form.size.widget:
                return
        else:
            self.fail("Size widget not focus")

    def test_create_partition(self):
        valid_data = {
            'size': "1M",
            'fstype': "ext4",
            }
        model, disk = make_model_and_disk()
        view, stretchy = make_partition_view(model, disk)
        view_helpers.enter_data(stretchy.form, valid_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        valid_data['mount'] = '/'
        valid_data['size'] = dehumanize_size(valid_data['size'])
        valid_data['use_swap'] = False
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, None, valid_data)

    def test_edit_partition(self):
        form_data = {
            'size': "256M",
            'fstype': "xfs",
            }
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, 512*(2**20))
        model.add_filesystem(partition, "ext4")
        view, stretchy = make_partition_view(model, disk, partition)
        self.assertTrue(stretchy.form.done_btn.enabled)
        view_helpers.enter_data(stretchy.form, form_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            'size': dehumanize_size(form_data['size']),
            'fstype': 'xfs',
            'mount': None,
            'use_swap': False,
            }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, stretchy.partition, expected_data)

    def test_size_clamping(self):
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, 512*(2**20))
        model.add_filesystem(partition, "ext4")
        view, stretchy = make_partition_view(model, disk, partition)
        self.assertTrue(stretchy.form.done_btn.enabled)
        stretchy.form.size.value = "1000T"
        stretchy.form.size.widget.lost_focus()
        self.assertTrue(stretchy.form.size.showing_extra)
        self.assertIn(
            "Capped partition size", stretchy.form.size.under_text.text)

    def test_edit_existing_partition(self):
        form_data = {
            'fstype': "xfs",
            }
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, 512*(2**20))
        partition.preserve = True
        model.add_filesystem(partition, "ext4")
        view, stretchy = make_partition_view(model, disk, partition)
        self.assertFalse(stretchy.form.size.enabled)
        self.assertTrue(stretchy.form.done_btn.enabled)
        view_helpers.enter_data(stretchy.form, form_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            'fstype': 'xfs',
            'mount': None,
            'use_swap': False,
            }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, stretchy.partition, expected_data)

    def test_edit_existing_partition_mountpoints(self):
        # Set up a PartitionStretchy for editing a partition with an
        # existing filesystem.
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, 512*(2**20))
        partition.preserve = True
        partition.number = 1
        fs = model.add_filesystem(partition, "ext4")
        model._orig_config = model._render_actions()
        fs.preserve = True
        view, stretchy = make_partition_view(model, disk, partition)
        self.assertFalse(stretchy.form.size.enabled)
        self.assertTrue(stretchy.form.done_btn.enabled)

        # By default, the "leave formatted as xxx" option is selected.
        self.assertIs(stretchy.form.fstype.value, None)
        # As is "leave unmounted"
        self.assertIs(stretchy.form.mount.value, None)

        # The option for mounting at / is disabled. But /srv is still
        # enabled.
        selector = stretchy.form.mount.widget._selector
        self.assertFalse(selector.option_by_value('/').enabled)
        self.assertTrue(selector.option_by_value('/srv').enabled)

        # Typing in an unsuitable mountpoint triggers a message.
        stretchy.form.mount.value = "/boot"
        stretchy.form.mount.validate()
        self.assertTrue(stretchy.form.mount.showing_extra)
        self.assertIn(
            "bad idea", stretchy.form.mount.under_text.text)
        self.assertIn(
            "/boot", stretchy.form.mount.under_text.text)

        # Selecting to reformat the partition clears the message and
        # reenables the / option.
        stretchy.form.select_fstype(None, "ext4")
        self.assertFalse(stretchy.form.mount.showing_extra)
        self.assertTrue(selector.option_by_value('/').enabled)

    def test_edit_boot_partition(self):
        form_data = {
            'size': "256M",
            }
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, 512*(2**20), "boot")
        fs = model.add_filesystem(partition, "fat32")
        model.add_mount(fs, '/boot/efi')
        view, stretchy = make_partition_view(model, disk, partition)

        self.assertFalse(stretchy.form.fstype.enabled)
        self.assertEqual(stretchy.form.fstype.value, "fat32")
        self.assertFalse(stretchy.form.mount.enabled)
        self.assertEqual(stretchy.form.mount.value, "/boot/efi")

        view_helpers.enter_data(stretchy.form, form_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            'size': dehumanize_size(form_data['size']),
            'fstype': "fat32",
            'mount': '/boot/efi',
            'use_swap': False,
            }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, stretchy.partition, expected_data)

    def test_edit_existing_unused_boot_partition(self):
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, 512*(2**20), "boot")
        fs = model.add_filesystem(partition, "fat32")
        model._orig_config = model._render_actions()
        disk.preserve = partition.preserve = fs.preserve = True
        view, stretchy = make_partition_view(model, disk, partition)

        self.assertFalse(stretchy.form.fstype.enabled)
        self.assertEqual(stretchy.form.fstype.value, None)
        self.assertFalse(stretchy.form.mount.enabled)
        self.assertEqual(stretchy.form.mount.value, None)

        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            'mount': None,
            'use_swap': False,
            }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, stretchy.partition, expected_data)

    def test_edit_existing_used_boot_partition(self):
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, 512*(2**20), "boot")
        fs = model.add_filesystem(partition, "fat32")
        model._orig_config = model._render_actions()
        partition.grub_device = True
        disk.preserve = partition.preserve = fs.preserve = True
        model.add_mount(fs, '/boot/efi')
        view, stretchy = make_partition_view(model, disk, partition)

        self.assertTrue(stretchy.form.fstype.enabled)
        self.assertEqual(stretchy.form.fstype.value, None)
        self.assertFalse(stretchy.form.mount.enabled)
        self.assertEqual(stretchy.form.mount.value, '/boot/efi')

        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            'fstype': None,
            'mount': '/boot/efi',
            'use_swap': False,
            }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, stretchy.partition, expected_data)

    def test_format_entire_unusual_filesystem(self):
        model, disk = make_model_and_disk()
        fs = model.add_filesystem(disk, "ntfs")
        fs.preserve = True
        model._orig_config = model._render_actions()
        view, stretchy = make_format_entire_view(model, disk)
        self.assertEqual(
            stretchy.form.fstype.value, None)
