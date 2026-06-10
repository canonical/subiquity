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

from subiquity.common.storage.requirements import (
    Requirements,
    RequirementSeverity,
    StorageRequirement,
)
from subiquity.models.tests.test_storage import make_model
from subiquitycore.tests.parameterized import parameterized


class TestStorageRequirement(unittest.TestCase):
    def test_init(self):
        req = StorageRequirement(
            guidance_message="msg",
            severity=RequirementSeverity.BLOCKING,
            check=lambda m: True,
            applies_to=lambda m: False,
        )
        self.assertEqual(req.guidance_message, "msg")
        self.assertEqual(req.severity, RequirementSeverity.BLOCKING)

    def test_is_applicable(self):
        req = StorageRequirement(
            guidance_message="msg",
            severity=RequirementSeverity.WARNING,
            check=lambda m: True,
            applies_to=lambda m: False,
        )
        self.assertFalse(req.is_applicable("model"))

    def test_is_satisfied(self):
        req = StorageRequirement(
            guidance_message="msg",
            severity=RequirementSeverity.WARNING,
            check=lambda m: False,
        )
        self.assertFalse(req.is_satisfied("model"))

    def test_is_violated__applicable_not_satisfied(self):
        req = StorageRequirement(
            guidance_message="msg",
            severity=RequirementSeverity.BLOCKING,
            check=lambda m: False,
            applies_to=lambda m: True,
        )
        self.assertTrue(req.is_violated("model"))

    def test_is_violated__not_applicable(self):
        req = StorageRequirement(
            guidance_message="msg",
            severity=RequirementSeverity.BLOCKING,
            check=lambda m: False,
            applies_to=lambda m: False,
        )
        self.assertFalse(req.is_violated("model"))

    def test_is_violated__satisfied(self):
        req = StorageRequirement(
            guidance_message="msg",
            severity=RequirementSeverity.BLOCKING,
            check=lambda m: True,
            applies_to=lambda m: True,
        )
        self.assertFalse(req.is_violated("model"))


class TestRequirements(unittest.TestCase):
    def test_all(self):
        all_reqs = Requirements.all()
        self.assertEqual(
            all_reqs,
            [
                Requirements.ROOT_MOUNTED,
                Requirements.REMOTE_BOOT_LOCAL,
                Requirements.BOOTLOADER_NEEDED,
            ],
        )

    def test_ROOT_MOUNTED_check(self):
        model = make_model()
        with mock.patch.object(model, "is_root_mounted", return_value=True):
            self.assertTrue(Requirements.ROOT_MOUNTED.is_satisfied(model))
        with mock.patch.object(model, "is_root_mounted", return_value=False):
            self.assertFalse(Requirements.ROOT_MOUNTED.is_satisfied(model))

    def test_BOOTLOADER_NEEDED_applies_to(self):
        self.assertTrue(Requirements.BOOTLOADER_NEEDED.is_applicable(make_model()))

    @parameterized.expand(
        (
            (True, False, True),
            (True, True, False),
            (False, False, False),
            (False, True, False),
        )
    )
    def test_REMOTE_BOOT_LOCAL_check(
        self, boot_mounted: bool, bootfs_remote: bool, expected: bool
    ):
        model = make_model()
        with (
            mock.patch.object(model, "is_boot_mounted", return_value=boot_mounted),
            mock.patch.object(
                model,
                "is_bootfs_on_remote_storage",
                return_value=bootfs_remote,
            ),
        ):
            self.assertEqual(
                expected, Requirements.REMOTE_BOOT_LOCAL.is_satisfied(model)
            )

    # Full truth table: applies only when root_mounted AND rootfs_remote
    # AND NOT nvme_tcp.  All other combinations should not apply.
    @parameterized.expand(
        (
            (False, False, False, False),
            (False, False, True, False),
            (False, True, False, False),
            (False, True, True, False),
            (True, False, False, False),
            (True, False, True, False),
            (True, True, False, True),
            (True, True, True, False),
        )
    )
    def test_REMOTE_BOOT_LOCAL_applies_to(
        self,
        root_mounted: bool,
        rootfs_remote: bool,
        nvme_tcp: bool,
        expected: bool,
    ):
        model = make_model()
        with (
            mock.patch.object(model, "is_root_mounted", return_value=root_mounted),
            mock.patch.object(
                model,
                "is_rootfs_on_remote_storage",
                return_value=rootfs_remote,
            ),
            mock.patch.object(
                type(model),
                "supports_nvme_tcp_booting",
                new_callable=mock.PropertyMock,
                return_value=nvme_tcp,
            ),
        ):
            self.assertEqual(
                expected, Requirements.REMOTE_BOOT_LOCAL.is_applicable(model)
            )

    def test_ROOT_MOUNTED_applies_to(self):
        self.assertTrue(Requirements.ROOT_MOUNTED.is_applicable(make_model()))

    def test_BOOTLOADER_NEEDED_check(self):
        model = make_model()
        with mock.patch.object(model, "needs_bootloader_partition", return_value=False):
            self.assertTrue(Requirements.BOOTLOADER_NEEDED.is_satisfied(model))
        with mock.patch.object(model, "needs_bootloader_partition", return_value=True):
            self.assertFalse(Requirements.BOOTLOADER_NEEDED.is_satisfied(model))
