import unittest
from unittest import mock

import urwid

from subiquity.client.controllers.filesystem import FilesystemController
from subiquity.common.filesystem import gaps
from subiquity.models.filesystem import MiB, dehumanize_size
from subiquity.models.tests.test_filesystem import make_model_and_disk
from subiquity.ui.mount import common_mountpoints, suitable_mountpoints_for_existing_fs
from subiquity.ui.views.filesystem.partition import (
    FormatEntireStretchy,
    PartitionForm,
    PartitionStretchy,
)
from subiquitycore.testing import view_helpers
from subiquitycore.tests.parameterized import parameterized
from subiquitycore.view import BaseView


def make_partition_view(model, disk, **kw):
    controller = mock.create_autospec(spec=FilesystemController)
    base_view = BaseView(urwid.Text(""))
    base_view.model = model
    base_view.controller = controller
    base_view.refresh_model_inputs = lambda: None
    stretchy = PartitionStretchy(base_view, disk, **kw)
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
        gap = gaps.Gap(device=disk, offset=1 << 20, size=99 << 30)
        view, stretchy = make_partition_view(model, disk, gap=gap)
        focus_path = view_helpers.get_focus_path(view)
        for w in reversed(focus_path):
            if w is stretchy.form.size.widget:
                return
        else:
            self.fail("Size widget not focus")

    def test_create_partition(self):
        valid_data = {
            "size": "1M",
            "fstype": "ext4",
        }
        model, disk = make_model_and_disk()
        gap = gaps.Gap(device=disk, offset=1 << 20, size=99 << 30)
        view, stretchy = make_partition_view(model, disk, gap=gap)
        view_helpers.enter_data(stretchy.form, valid_data)
        stretchy.form.size.widget.lost_focus()
        view_helpers.click(stretchy.form.done_btn.base_widget)
        valid_data["mount"] = "/"
        valid_data["size"] = dehumanize_size(valid_data["size"])
        valid_data["use_swap"] = False
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, valid_data, partition=None, gap=gap
        )

    def test_edit_partition(self):
        form_data = {
            "size": "256M",
            "fstype": "xfs",
        }
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, size=512 * (2**20), offset=0)
        model.add_filesystem(partition, "ext4")
        view, stretchy = make_partition_view(model, disk, partition=partition)
        self.assertTrue(stretchy.form.done_btn.enabled)
        view_helpers.enter_data(stretchy.form, form_data)
        stretchy.form.size.widget.lost_focus()
        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            "size": dehumanize_size(form_data["size"]),
            "fstype": "xfs",
            "mount": None,
            "use_swap": False,
        }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, expected_data, partition=stretchy.partition, gap=None
        )

    def test_size_clamping(self):
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, size=512 * (2**20), offset=0)
        model.add_filesystem(partition, "ext4")
        view, stretchy = make_partition_view(model, disk, partition=partition)
        self.assertTrue(stretchy.form.done_btn.enabled)
        stretchy.form.size.value = "1000T"
        stretchy.form.size.widget.lost_focus()
        self.assertTrue(stretchy.form.size.showing_extra)
        self.assertIn("Capped partition size", stretchy.form.size.under_text.text)

    def test_edit_existing_partition(self):
        form_data = {
            "fstype": "xfs",
        }
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, size=512 * (2**20), offset=0)
        partition.preserve = True
        model.add_filesystem(partition, "ext4")
        view, stretchy = make_partition_view(model, disk, partition=partition)
        self.assertFalse(stretchy.form.size.enabled)
        self.assertTrue(stretchy.form.done_btn.enabled)
        view_helpers.enter_data(stretchy.form, form_data)
        stretchy.form.size.widget.lost_focus()
        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            "fstype": "xfs",
            "mount": None,
            "use_swap": False,
        }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, expected_data, partition=stretchy.partition, gap=None
        )

    def test_edit_existing_partition_mountpoints(self):
        # Set up a PartitionStretchy for editing a partition with an
        # existing filesystem.
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, size=512 * (2**20), offset=0)
        partition.preserve = True
        partition.number = 1
        fs = model.add_filesystem(partition, "ext4")
        model._orig_config = model._render_actions()
        fs.preserve = True
        view, stretchy = make_partition_view(model, disk, partition=partition)
        self.assertFalse(stretchy.form.size.enabled)
        self.assertTrue(stretchy.form.done_btn.enabled)

        # By default, the "leave formatted as xxx" option is selected.
        self.assertIs(stretchy.form.fstype.value, None)
        # As is "leave unmounted"
        self.assertIs(stretchy.form.mount.value, None)

        # The option for mounting at / is disabled. But /srv is still
        # enabled.
        selector = stretchy.form.mount.widget._selector
        self.assertFalse(selector.option_by_value("/").enabled)
        self.assertTrue(selector.option_by_value("/srv").enabled)

        # Typing in an unsuitable mountpoint triggers a message.
        stretchy.form.mount.value = "/boot"
        stretchy.form.mount.validate()
        self.assertTrue(stretchy.form.mount.showing_extra)
        self.assertIn("bad idea", stretchy.form.mount.under_text.text)
        self.assertIn("/boot", stretchy.form.mount.under_text.text)

        # Selecting to reformat the partition clears the message and
        # reenables the / option.
        stretchy.form.select_fstype(None, "ext4")
        self.assertFalse(stretchy.form.mount.showing_extra)
        self.assertTrue(selector.option_by_value("/").enabled)

    def test_edit_boot_partition(self):
        form_data = {
            "size": "256M",
        }
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, size=512 * (2**20), offset=0, flag="boot")
        fs = model.add_filesystem(partition, "fat32")
        model.add_mount(fs, "/boot/efi")
        view, stretchy = make_partition_view(model, disk, partition=partition)

        self.assertFalse(stretchy.form.fstype.enabled)
        self.assertEqual(stretchy.form.fstype.value, "fat32")
        self.assertFalse(stretchy.form.mount.enabled)
        self.assertEqual(stretchy.form.mount.value, "/boot/efi")

        view_helpers.enter_data(stretchy.form, form_data)
        stretchy.form.size.widget.lost_focus()
        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            "size": dehumanize_size(form_data["size"]),
            "fstype": "fat32",
            "mount": "/boot/efi",
            "use_swap": False,
        }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, expected_data, partition=stretchy.partition, gap=None
        )

    def test_edit_existing_unused_boot_partition(self):
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, size=512 * (2**20), offset=0, flag="boot")
        fs = model.add_filesystem(partition, "fat32")
        model._orig_config = model._render_actions()
        disk.preserve = partition.preserve = fs.preserve = True
        view, stretchy = make_partition_view(model, disk, partition=partition)

        self.assertFalse(stretchy.form.fstype.enabled)
        self.assertEqual(stretchy.form.fstype.value, None)
        self.assertFalse(stretchy.form.mount.enabled)
        self.assertEqual(stretchy.form.mount.value, None)

        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            "mount": None,
            "use_swap": False,
        }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, expected_data, partition=stretchy.partition, gap=None
        )

    def test_edit_existing_used_boot_partition(self):
        model, disk = make_model_and_disk()
        partition = model.add_partition(disk, size=512 * (2**20), offset=0, flag="boot")
        fs = model.add_filesystem(partition, "fat32")
        model._orig_config = model._render_actions()
        partition.grub_device = True
        disk.preserve = partition.preserve = fs.preserve = True
        model.add_mount(fs, "/boot/efi")
        view, stretchy = make_partition_view(model, disk, partition=partition)

        self.assertTrue(stretchy.form.fstype.enabled)
        self.assertEqual(stretchy.form.fstype.value, None)
        self.assertFalse(stretchy.form.mount.enabled)
        self.assertEqual(stretchy.form.mount.value, "/boot/efi")

        view_helpers.click(stretchy.form.done_btn.base_widget)
        expected_data = {
            "fstype": None,
            "mount": "/boot/efi",
            "use_swap": False,
        }
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, expected_data, partition=stretchy.partition, gap=None
        )

    def test_format_entire_unusual_filesystem(self):
        model, disk = make_model_and_disk()
        fs = model.add_filesystem(disk, "ntfs")
        fs.preserve = True
        model._orig_config = model._render_actions()
        view, stretchy = make_format_entire_view(model, disk)
        self.assertEqual(stretchy.form.fstype.value, None)

    def test_create_partition_unaligned_size(self):
        # In LP: #2013201, the user would type in 1.1G and the partition
        # created would not be aligned to a MiB boundary.
        unaligned_data = {
            "size": "1.1G",  # Corresponds to 1181116006.4 bytes (not an int)
            "fstype": "ext4",
        }
        valid_data = {
            "mount": "/",
            "size": 1127 * MiB,  # ~1.10058 GiB
            "use_swap": False,
            "fstype": "ext4",
        }
        model, disk = make_model_and_disk()
        gap = gaps.Gap(device=disk, offset=1 << 20, size=99 << 30)
        view, stretchy = make_partition_view(model, disk, gap=gap)
        view_helpers.enter_data(stretchy.form, unaligned_data)
        stretchy.form.size.widget.lost_focus()
        view_helpers.click(stretchy.form.done_btn.base_widget)
        view.controller.partition_disk_handler.assert_called_once_with(
            stretchy.disk, valid_data, partition=None, gap=gap
        )


class TestPartitionForm(unittest.TestCase):
    def _make_name_form(self, lvm_names, name_value):
        form = mock.MagicMock(spec=PartitionForm)
        form.lvm_names = lvm_names
        form.name.value = name_value
        return form

    def _make_mount_form(
        self,
        mount_value,
        *,
        mountpoints=None,
        existing_fs_type=None,
        fstype_value="ext4",
        remote_storage=False,
    ):
        form = mock.MagicMock(spec=PartitionForm)
        form.mount.value = mount_value
        form.mountpoints = mountpoints if mountpoints is not None else {}
        form.existing_fs_type = existing_fs_type
        form.fstype.value = fstype_value
        form.remote_storage = remote_storage
        return form

    def _make_size_form(self, size_str, max_size):
        form = mock.MagicMock(spec=PartitionForm)
        form.size_str = size_str
        form.max_size = max_size
        return form

    def _make_clean_mount_form(self, is_mounted):
        form = mock.MagicMock()
        form.model.is_mounted_filesystem.return_value = is_mounted
        return form

    def test_validate_name__no_lvm(self):
        # When lvm_names is None the partition is not an LV; any name is accepted.
        form = self._make_name_form(None, "")
        self.assertIsNone(PartitionForm.validate_name(form))

    @parameterized.expand(
        [
            ["empty", set(), ""],
            ["starts_with_hyphen", set(), "-bad"],
            ["reserved_dot", set(), "."],
            ["reserved_dotdot", set(), ".."],
            ["reserved_snapshot", set(), "snapshot"],
            ["reserved_pvmove", set(), "pvmove"],
            ["reserved_substring_cdata", set(), "lv_cdata"],
            ["reserved_substring_cmeta", set(), "lv_cmeta"],
            ["reserved_substring_corig", set(), "lv_corig"],
            ["reserved_substring_mlog", set(), "lv_mlog"],
            ["reserved_substring_mimage", set(), "lv_mimage"],
            ["reserved_substring_pmspare", set(), "lv_pmspare"],
            ["reserved_substring_rimage", set(), "lv_rimage"],
            ["reserved_substring_rmeta", set(), "lv_rmeta"],
            ["reserved_substring_tdata", set(), "lv_tdata"],
            ["reserved_substring_tmeta", set(), "lv_tmeta"],
            ["reserved_substring_vorigin", set(), "lv_vorigin"],
            ["duplicate", {"existing-lv"}, "existing-lv"],
        ]
    )
    def test_validate_name__invalid(self, _name, lvm_names, name_value):
        form = self._make_name_form(lvm_names, name_value)
        self.assertIsNotNone(PartitionForm.validate_name(form))

    def test_validate_name__valid(self):
        form = self._make_name_form({"other-lv"}, "my-lv")
        self.assertIsNone(PartitionForm.validate_name(form))

    def test_validate_mount__none(self):
        # None mount value means "leave unmounted"; always accepted.
        form = self._make_mount_form(None)
        self.assertIsNone(PartitionForm.validate_mount(form))

    def test_validate_mount__error_path_too_long(self):
        form = self._make_mount_form("a" * 4096)
        self.assertIsNotNone(PartitionForm.validate_mount(form))

    def test_validate_mount__error_already_mounted(self):
        form = self._make_mount_form(
            "/home", mountpoints={"/home": mock.sentinel.device}
        )
        with mock.patch(
            "subiquity.ui.views.filesystem.partition.labels.label",
            return_value="sda",
        ):
            self.assertIsNotNone(PartitionForm.validate_mount(form))

    def test_validate_mount__valid(self):
        form = self._make_mount_form("/home")
        self.assertIsNone(PartitionForm.validate_mount(form))

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
        self.assertIsNone(PartitionForm.validate_mount(form))
        form.mount.show_extra.assert_called_once()

    def test_validate_mount__no_warning_existing_fs_suitable_mountpoint(self):
        # Mounting an existing filesystem at a suitable mountpoint shows no warning.
        form = self._make_mount_form(
            "/home",
            existing_fs_type="ext4",
            fstype_value=None,
        )
        self.assertIsNone(PartitionForm.validate_mount(form))
        form.mount.show_extra.assert_not_called()

    @parameterized.expand([["boot", "/boot"], ["boot_efi", "/boot/efi"]])
    def test_validate_mount__warning_remote_storage(self, _name, mount):
        form = self._make_mount_form(mount, remote_storage=True)
        self.assertIsNone(PartitionForm.validate_mount(form))
        form.mount.show_extra.assert_called_once()

    @parameterized.expand(
        [
            ["empty", ""],
            ["equal_to_size_str", "1.00G"],
        ]
    )
    def test_clean_size__returns_max(self, _name, val):
        max_size = 1 << 30
        form = self._make_size_form("1.00G", max_size)
        self.assertEqual(max_size, PartitionForm.clean_size(form, val))

    @parameterized.expand(
        [
            ["with_suffix", "512M"],
            ["no_suffix_uses_size_str_unit", "512"],
        ]
    )
    def test_clean_size__returns_parsed(self, _name, val):
        form = self._make_size_form("1.00G", 1 << 30)
        result = PartitionForm.clean_size(form, val)
        expected = dehumanize_size(val if val[-1].isalpha() else val + "G")
        self.assertEqual(expected, result)

    def test_clean_mount__mounted_filesystem_returns_path(self):
        form = self._make_clean_mount_form(is_mounted=True)
        self.assertEqual("/home", PartitionForm.clean_mount(form, "/home"))

    def test_clean_mount__unmounted_filesystem_returns_none(self):
        form = self._make_clean_mount_form(is_mounted=False)
        self.assertIsNone(PartitionForm.clean_mount(form, "/home"))
