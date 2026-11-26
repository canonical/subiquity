# Copyright 2025 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import unittest
from unittest import mock
from unittest.mock import patch

from subiquity.client.controllers.storage import StorageController
from subiquity.common.types.storage import (
    Disk,
    GuidedCapability,
    GuidedDisallowedCapability,
    GuidedDisallowedCapabilityReason,
    GuidedStorageTargetManual,
    GuidedStorageTargetReformat,
    RecoveryKey,
)
from subiquity.ui.views.storage.guided import (
    GuidedDiskSelectionView,
    GuidedLVMView,
    summarize_device,
)
from subiquitycore.testing import view_helpers


def make_disk(disk_id="sda", has_in_use_partition=False):
    return Disk(
        id=disk_id,
        label=disk_id,
        type="local disk",
        size=500 * (1 << 30),
        usage_labels=[],
        partitions=[],
        ok_for_guided=True,
        ptable="gpt",
        preserve=False,
        path="/dev/" + disk_id,
        boot_device=False,
        can_be_boot_device=True,
        model="",
        vendor="",
        has_in_use_partition=has_in_use_partition,
        requires_reformat=False,
    )


def make_target(disk_id="sda", allowed=None, disallowed=None):
    return GuidedStorageTargetReformat(
        disk_id=disk_id,
        allowed=allowed or [],
        disallowed=disallowed or [],
    )


def make_controller():
    return mock.create_autospec(spec=StorageController)


CLASSIC = [GuidedCapability.DIRECT, GuidedCapability.LVM, GuidedCapability.LVM_LUKS]


class TestGuidedSummarizeDevice(unittest.TestCase):
    def test_install_media(self):
        d = Disk(
            id="disk-vda",
            label="My disk",
            type="local disk",
            size=1 << 30,
            usage_labels=["already formatted as iso9660", "in use"],
            partitions=[],
            ok_for_guided=True,
            ptable="gpt",
            preserve=True,
            path="/dev/vda",
            boot_device=False,
            can_be_boot_device=True,
            has_in_use_partition=True,
        )

        # In urwid, comparing two Text instances evaluates to false even if the
        # content is the same.
        # urwid.Text("foo") != urwid.Text("foo")
        # Let's define a function that will return True if args are the same.
        def noop(*args, **kwargs):
            return *args, dict(**kwargs)

        Text = noop
        # Also urwid will be unhappy if we don't pass a real Text instance to
        # info_minor, so mock it as well.
        info_minor = noop

        p_text = patch("subiquity.ui.views.storage.guided.Text", side_effect=Text)
        p_info_minor = patch(
            "subiquity.ui.views.storage.guided.Color.info_minor",
            side_effect=info_minor,
        )

        with p_text as m_text, p_info_minor as m_info_minor:
            row_disk, row_usage_labels = summarize_device(d)

        self.assertIsNone(row_disk[0])
        self.assertEqual(row_disk[1][0], (2, Text("My disk")))
        self.assertEqual(row_disk[1][1], Text("local disk"))
        self.assertEqual(row_disk[1][2], Text("1.000G", align="right"))

        self.assertIsNone(row_usage_labels[0])
        self.assertEqual(
            row_usage_labels[1][0],
            (4, info_minor(Text("already formatted as iso9660, in use"))),
        )

        m_text.assert_called()
        m_info_minor.assert_called_once()


class GuidedDiskSelectionViewTests(unittest.TestCase):
    def test_classic_disk_shows_direct_and_lvm_no_tpm(self):
        disk = make_disk()
        target = make_target(allowed=CLASSIC)
        view = GuidedDiskSelectionView(make_controller(), [target], {disk.id: disk})

        names = [bf.field.name for bf in view.form._fields]
        self.assertIn("choice_direct", names)
        self.assertIn("choice_lvm", names)
        self.assertNotIn("choice_tpm", names)
        self.assertNotIn("choice_core_boot_classic_encrypted", names)
        self.assertNotIn("choice_core_boot_classic_unencrypted", names)
        # Custom is not offered unless a manual target is present.
        self.assertNotIn("choice_custom", names)

    def test_classic_disk_defaults_to_lvm(self):
        disk = make_disk()
        target = make_target(allowed=CLASSIC)
        view = GuidedDiskSelectionView(make_controller(), [target], {disk.id: disk})

        self.assertFalse(view.form.choice_direct.value)
        self.assertTrue(view.form.choice_lvm.value)

    def test_lvm_choice_routes_to_guided_lvm(self):
        disk = make_disk()
        target = make_target(allowed=CLASSIC)
        controller = make_controller()
        view = GuidedDiskSelectionView(controller, [target], {disk.id: disk})

        view.done(None)

        controller.guided_lvm.assert_called_once_with(target, {disk.id: disk})
        controller.guided_choice.assert_not_called()

    def test_direct_choice_routes_to_direct(self):
        disk = make_disk()
        target = make_target(allowed=CLASSIC)
        controller = make_controller()
        view = GuidedDiskSelectionView(controller, [target], {disk.id: disk})
        view.form.choice_direct.widget.set_state(True)

        view.done(None)

        controller.guided_choice.assert_called_once()
        choice = controller.guided_choice.call_args.args[0]
        self.assertEqual(choice.capability, GuidedCapability.DIRECT)
        self.assertEqual(choice.target, target)
        controller.guided_lvm.assert_not_called()

    def test_dd_choice_routes_to_dd(self):
        disk = make_disk()
        target = make_target(allowed=[GuidedCapability.DD])
        controller = make_controller()
        view = GuidedDiskSelectionView(controller, [target], {disk.id: disk})

        view.done(None)

        choice = controller.guided_choice.call_args.args[0]
        self.assertEqual(choice.capability, GuidedCapability.DD)

    def test_tpm_encrypted_routes_to_core_boot_encrypted(self):
        disk = make_disk()
        target = make_target(allowed=[GuidedCapability.CORE_BOOT_ENCRYPTED])
        controller = make_controller()
        view = GuidedDiskSelectionView(controller, [target], {disk.id: disk})

        names = [bf.field.name for bf in view.form._fields]
        self.assertIn("choice_core_boot_classic_encrypted", names)
        self.assertTrue(view.form.choice_core_boot_classic_encrypted.value)
        self.assertNotIn("choice_core_boot_classic_unencrypted", names)

        view.done(None)

        choice = controller.guided_choice.call_args.args[0]
        self.assertEqual(choice.capability, GuidedCapability.CORE_BOOT_ENCRYPTED)

    def test_tpm_unencrypted_only_routes_to_core_boot_unencrypted(self):
        disk = make_disk()
        target = make_target(
            allowed=[GuidedCapability.CORE_BOOT_UNENCRYPTED],
            disallowed=[
                GuidedDisallowedCapability(
                    capability=GuidedCapability.CORE_BOOT_ENCRYPTED,
                    reason=GuidedDisallowedCapabilityReason.CORE_BOOT_ENCRYPTION_UNAVAILABLE,
                    message="TPM not found",
                )
            ],
        )
        controller = make_controller()
        view = GuidedDiskSelectionView(controller, [target], {disk.id: disk})

        names = [bf.field.name for bf in view.form._fields]
        self.assertIn("choice_core_boot_classic_unencrypted", names)
        self.assertTrue(view.form.choice_core_boot_classic_unencrypted.value)
        self.assertFalse(view.form.choice_core_boot_classic_encrypted.enabled)
        self.assertEqual(
            view.form.choice_core_boot_classic_encrypted.help, "TPM not found"
        )

        view.done(None)

        choice = controller.guided_choice.call_args.args[0]
        self.assertEqual(choice.capability, GuidedCapability.CORE_BOOT_UNENCRYPTED)

    def test_tpm_prefer_encrypted_shows_both_radios(self):
        disk = make_disk()
        target = make_target(allowed=[GuidedCapability.CORE_BOOT_PREFER_ENCRYPTED])
        view = GuidedDiskSelectionView(make_controller(), [target], {disk.id: disk})

        names = [bf.field.name for bf in view.form._fields]
        self.assertIn("choice_core_boot_classic_encrypted", names)
        self.assertIn("choice_core_boot_classic_unencrypted", names)
        self.assertTrue(view.form.choice_core_boot_classic_encrypted.value)
        self.assertFalse(view.form.choice_core_boot_classic_unencrypted.value)

    def test_tpm_prefer_unencrypted_shows_both_radios(self):
        disk = make_disk()
        target = make_target(allowed=[GuidedCapability.CORE_BOOT_PREFER_UNENCRYPTED])
        view = GuidedDiskSelectionView(make_controller(), [target], {disk.id: disk})

        names = [bf.field.name for bf in view.form._fields]
        self.assertIn("choice_core_boot_classic_encrypted", names)
        self.assertIn("choice_core_boot_classic_unencrypted", names)
        self.assertFalse(view.form.choice_core_boot_classic_encrypted.value)
        self.assertTrue(view.form.choice_core_boot_classic_unencrypted.value)

    def test_custom_choice_routes_to_manual(self):
        disk = make_disk()
        target = make_target(allowed=CLASSIC)
        controller = make_controller()
        view = GuidedDiskSelectionView(
            controller, [target, GuidedStorageTargetManual()], {disk.id: disk}
        )
        self.assertTrue(view.form._field_present("choice_custom"))
        view.form.choice_custom.widget.set_state(True)

        view.done(None)

        choice = controller.guided_choice.call_args.args[0]
        self.assertEqual(choice.capability, GuidedCapability.MANUAL)
        self.assertIsInstance(choice.target, GuidedStorageTargetManual)

    def test_back_calls_cancel(self):
        disk = make_disk()
        target = make_target(allowed=CLASSIC)
        controller = make_controller()
        view = GuidedDiskSelectionView(controller, [target], {disk.id: disk})

        view.cancel(None)

        controller.cancel.assert_called_once()

    def test_only_one_radio_selected_by_default(self):
        disk = make_disk()
        target = make_target(allowed=CLASSIC)
        view = GuidedDiskSelectionView(make_controller(), [target], {disk.id: disk})

        selected = [
            name
            for name in (
                "choice_direct",
                "choice_lvm",
                "choice_tpm",
                "choice_core_boot_classic_encrypted",
                "choice_core_boot_classic_unencrypted",
                "choice_custom",
            )
            if view.form._field_present(name) and getattr(view.form, name).value
        ]
        self.assertEqual(selected, ["choice_lvm"])

    def test_disk_change_preserves_valid_radio_selection(self):
        disk1 = make_disk("sda")
        disk2 = make_disk("sdb")
        target1 = make_target("sda", allowed=CLASSIC)
        target2 = make_target("sdb", allowed=CLASSIC)
        view = GuidedDiskSelectionView(
            make_controller(),
            [target1, target2],
            {"sda": disk1, "sdb": disk2},
        )
        # User picks "Guided — use entire disk" (no LVM).
        view.form.choice_direct.widget.set_state(True)
        self.assertTrue(view.form.choice_direct.value)
        self.assertFalse(view.form.choice_lvm.value)

        # Switching to the other disk must preserve the direct choice. Simulate
        # the selector's "select" signal firing (as a real popup pick does).
        view.form._select_disk(None, target2)

        self.assertTrue(view.form.choice_direct.value)
        self.assertFalse(view.form.choice_lvm.value)

    def test_disk_change_falls_back_when_choice_becomes_invalid(self):
        # disk1 supports LVM; disk2 only supports DIRECT (no LVM).
        disk1 = make_disk("sda")
        disk2 = make_disk("sdb")
        target1 = make_target("sda", allowed=CLASSIC)
        target2 = make_target("sdb", allowed=[GuidedCapability.DIRECT])
        view = GuidedDiskSelectionView(
            make_controller(),
            [target1, target2],
            {"sda": disk1, "sdb": disk2},
        )
        # Default for disk1 is LVM.
        self.assertTrue(view.form.choice_lvm.value)

        # Switching to disk2 (no LVM) must fall back to direct.
        view.form._select_disk(None, target2)

        self.assertFalse(view.form.choice_lvm.enabled)
        self.assertTrue(view.form.choice_direct.value)


def make_lvm_target(disk_id="sda"):
    return GuidedStorageTargetReformat(
        disk_id=disk_id,
        allowed=[GuidedCapability.LVM, GuidedCapability.LVM_LUKS],
        disallowed=[],
    )


class GuidedLVMViewTests(unittest.TestCase):
    def test_defaults_to_no_encryption(self):
        disk = make_disk()
        target = make_lvm_target()
        view = GuidedLVMView(make_controller(), target, {disk.id: disk})

        self.assertTrue(view.form.encrypt_off.value)
        self.assertFalse(view.form.encrypt_on.value)
        self.assertFalse(view.form.passphrase.enabled)
        self.assertFalse(view.form.confirm_passphrase.enabled)
        self.assertFalse(view.form.recovery_key.enabled)

    def test_no_encrypt_routes_to_lvm(self):
        disk = make_disk()
        target = make_lvm_target()
        controller = make_controller()
        view = GuidedLVMView(controller, target, {disk.id: disk})

        view.done(None)

        controller.guided_choice.assert_called_once()
        choice = controller.guided_choice.call_args.args[0]
        self.assertEqual(choice.capability, GuidedCapability.LVM)
        self.assertIsNone(choice.password)
        self.assertIsNone(choice.recovery_key)

    def test_encrypt_routes_to_lvm_luks(self):
        disk = make_disk()
        target = make_lvm_target()
        controller = make_controller()
        view = GuidedLVMView(controller, target, {disk.id: disk})
        view.form.encrypt_on.widget.set_state(True)
        view_helpers.enter_data(
            view.form,
            {
                "passphrase": "passw0rd",
                "confirm_passphrase": "passw0rd",
                "recovery_key": False,
            },
        )

        view.done(None)

        choice = controller.guided_choice.call_args.args[0]
        self.assertEqual(choice.capability, GuidedCapability.LVM_LUKS)
        self.assertEqual(choice.password, "passw0rd")
        self.assertIsNone(choice.recovery_key)

    def test_encrypt_with_recovery_key(self):
        disk = make_disk()
        target = make_lvm_target()
        controller = make_controller()
        view = GuidedLVMView(controller, target, {disk.id: disk})
        view.form.encrypt_on.widget.set_state(True)
        view_helpers.enter_data(
            view.form,
            {
                "passphrase": "passw0rd",
                "confirm_passphrase": "passw0rd",
                "recovery_key": True,
            },
        )

        view.done(None)

        choice = controller.guided_choice.call_args.args[0]
        self.assertEqual(choice.capability, GuidedCapability.LVM_LUKS)
        self.assertIsInstance(choice.recovery_key, RecoveryKey)

    def test_mismatched_passphrase_invalid(self):
        disk = make_disk()
        target = make_lvm_target()
        view = GuidedLVMView(make_controller(), target, {disk.id: disk})
        view.form.encrypt_on.widget.set_state(True)
        view_helpers.enter_data(
            view.form,
            {
                "passphrase": "passw0rd",
                "confirm_passphrase": "different",
                "recovery_key": False,
            },
        )

        # The form framework only re-runs a field's validator on change when it
        # is already in-error/showing-extra, so force a validation here.
        view.form.confirm_passphrase.validate()
        self.assertTrue(view.form.confirm_passphrase.in_error)
        self.assertTrue(view.form.has_validation_error())

    def test_matching_passphrase_valid(self):
        disk = make_disk()
        target = make_lvm_target()
        view = GuidedLVMView(make_controller(), target, {disk.id: disk})
        view.form.encrypt_on.widget.set_state(True)
        view_helpers.enter_data(
            view.form,
            {
                "passphrase": "passw0rd",
                "confirm_passphrase": "passw0rd",
                "recovery_key": False,
            },
        )

        self.assertIsNone(view.form.validate_confirm_passphrase())
        self.assertFalse(view.form.has_validation_error())

    def test_encrypt_with_no_passphrase_invalid(self):
        disk = make_disk()
        target = make_lvm_target()
        view = GuidedLVMView(make_controller(), target, {disk.id: disk})
        view.form.encrypt_on.widget.set_state(True)

        # Toggling encryption on must flag the empty passphrase as invalid so
        # the Done button stays disabled.
        self.assertTrue(view.form.passphrase.in_error)
        self.assertTrue(view.form.has_validation_error())

    def test_back_calls_cancel(self):
        disk = make_disk()
        target = make_lvm_target()
        controller = make_controller()
        view = GuidedLVMView(controller, target, {disk.id: disk})

        view.cancel(None)

        controller.cancel.assert_called_once()
