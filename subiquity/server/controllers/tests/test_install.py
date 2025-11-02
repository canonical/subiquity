# Copyright 2022 Canonical, Ltd.
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

import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import ANY, AsyncMock, Mock, call, mock_open, patch

from curtin.util import EFIBootEntry, EFIBootState

from subiquity.common.types import PackageInstallState
from subiquity.models.identity import DefaultGroups, User
from subiquity.models.tests.test_filesystem import make_model_and_partition
from subiquity.server.controllers.install import CurtinInstallError, InstallController
from subiquity.server.mounter import Mountpoint
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


class TestWriteConfig(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.controller = InstallController(make_app())
        self.controller.write_config = unittest.mock.Mock()
        self.controller.app.note_file_for_apport = Mock()

        self.controller.model.target = "/target"

    @patch("subiquity.server.controllers.install.run_curtin_command")
    async def test_run_curtin_install_step(self, run_cmd):
        with patch("subiquity.server.controllers.install.open", mock_open()) as m_open:
            await self.controller.run_curtin_step(
                name="MyStep",
                stages=["partitioning", "extract"],
                config_file=Path("/config.yaml"),
                source="/source",
                config=self.controller.base_config(
                    logs_dir=Path("/"), resume_data_file=Path("resume-data")
                ),
            )

        m_open.assert_called_once_with("/curtin-install.log", mode="a")

        run_cmd.assert_called_once_with(
            self.controller.app,
            ANY,
            "install",
            "--set",
            'json:stages=["partitioning", "extract"]',
            "/source",
            config="/config.yaml",
            private_mounts=False,
        )

    @patch("subiquity.server.controllers.install.run_curtin_command")
    async def test_run_curtin_install_step_no_src(self, run_cmd):
        with patch("subiquity.server.controllers.install.open", mock_open()) as m_open:
            await self.controller.run_curtin_step(
                name="MyStep",
                stages=["partitioning", "extract"],
                config_file=Path("/config.yaml"),
                source=None,
                config=self.controller.base_config(
                    logs_dir=Path("/"), resume_data_file=Path("resume-data")
                ),
            )

        m_open.assert_called_once_with("/curtin-install.log", mode="a")

        run_cmd.assert_called_once_with(
            self.controller.app,
            ANY,
            "install",
            "--set",
            'json:stages=["partitioning", "extract"]',
            config="/config.yaml",
            private_mounts=False,
        )

    @patch("subiquity.server.controllers.install.open", mock_open())
    async def test_run_curtin_install_step_failed(self):
        cmd = ["curtin", "install", "--set", 'json:stages=["partitioning"]']
        stages = ["partitioning"]

        async def fake_run_curtin_command(*args, **kwargs):
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

        with patch(
            "subiquity.server.controllers.install.run_curtin_command",
            fake_run_curtin_command,
        ):
            with self.assertRaises(CurtinInstallError) as exc_cm:
                await self.controller.run_curtin_step(
                    name="MyStep",
                    stages=stages,
                    config_file=Path("/config.yaml"),
                    source=None,
                    config=self.controller.base_config(
                        logs_dir=Path("/"), resume_data_file=Path("resume-data")
                    ),
                )
        self.assertEqual(stages, exc_cm.exception.stages)
        self.assertEqual(cmd, exc_cm.exception.__context__.cmd)

    def test_base_config(self):
        config = self.controller.base_config(
            logs_dir=Path("/logs"), resume_data_file=Path("resume-data")
        )

        self.assertDictEqual(
            config,
            {
                "install": {
                    "target": "/target",
                    "unmount": "disabled",
                    "save_install_config": False,
                    "save_install_log": False,
                    "log_file": "/logs/curtin-install.log",
                    "log_file_append": True,
                    "error_tarfile": "/logs/curtin-errors.tar",
                    "resume_data": "resume-data",
                }
            },
        )

    def test_generic_config(self):
        with patch.object(
            self.controller.model, "render", return_value={"key": "value"}
        ):
            config = self.controller.generic_config(key2="value2")

        self.assertEqual(
            config,
            {
                "key": "value",
                "key2": "value2",
            },
        )


efi_state_no_rp = EFIBootState(
    current="0000",
    timeout="0 seconds",
    order=["0000", "0002"],
    entries={
        "0000": EFIBootEntry(
            name="ubuntu", path="HD(1,GPT,...)/File(\\EFI\\ubuntu\\shimx64.efi)"
        ),
        "0001": EFIBootEntry(
            name="Windows Boot Manager",
            path="HD(1,GPT,...,0x82000)/File(\\EFI\\bootmgfw.efi",
        ),
        "0002": EFIBootEntry(
            name="Linux-Firmware-Updater",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)\\.fwupd",
        ),
    },
)

efi_state_with_rp = EFIBootState(
    current="0000",
    timeout="0 seconds",
    order=["0000", "0002", "0003"],
    entries={
        "0000": EFIBootEntry(
            name="ubuntu", path="HD(1,GPT,...)/File(\\EFI\\ubuntu\\shimx64.efi)"
        ),
        "0001": EFIBootEntry(
            name="Windows Boot Manager",
            path="HD(1,GPT,...,0x82000)/File(\\EFI\\bootmgfw.efi",
        ),
        "0002": EFIBootEntry(
            name="Linux-Firmware-Updater",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)\\.fwupd",
        ),
        "0003": EFIBootEntry(
            name="Restore Ubuntu to factory state",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)",
        ),
    },
)

efi_state_with_dup_rp = EFIBootState(
    current="0000",
    timeout="0 seconds",
    order=["0000", "0002", "0004"],
    entries={
        "0000": EFIBootEntry(
            name="ubuntu", path="HD(1,GPT,...)/File(\\EFI\\ubuntu\\shimx64.efi)"
        ),
        "0001": EFIBootEntry(
            name="Windows Boot Manager",
            path="HD(1,GPT,...,0x82000)/File(\\EFI\\bootmgfw.efi",
        ),
        "0002": EFIBootEntry(
            name="Linux-Firmware-Updater",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)\\.fwupd",
        ),
        "0003": EFIBootEntry(
            name="Restore Ubuntu to factory state",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)",
        ),
        "0004": EFIBootEntry(
            name="Restore Ubuntu to factory state",
            path="HD(1,GPT,...,0x800,0x100000)/File(\\shimx64.efi)",
        ),
    },
)


class TestInstallController(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.controller = InstallController(make_app())
        self.controller.model.target = tempfile.mkdtemp()
        self.controller.app.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.controller.model.target, "etc/grub.d"))
        self.addCleanup(shutil.rmtree, self.controller.model.target)
        self.addCleanup(shutil.rmtree, self.controller.app.root)

    @patch("asyncio.sleep")
    async def test_install_package(self, m_sleep):
        run_curtin = "subiquity.server.controllers.install.run_curtin_command"
        error = subprocess.CalledProcessError(
            returncode=1, cmd="curtin system-install git"
        )

        with patch(run_curtin):
            await self.controller.install_package(package="git")
            m_sleep.assert_not_called()

        m_sleep.reset_mock()
        with patch(run_curtin, side_effect=(error, None, None)):
            await self.controller.install_package(package="git")
            m_sleep.assert_called_once()

        m_sleep.reset_mock()
        with patch(run_curtin, side_effect=(error, error, error, error)):
            with self.assertRaises(subprocess.CalledProcessError):
                await self.controller.install_package(package="git")

    def setup_rp_test(self, lsblk_output=b"lsblk_output"):
        app = self.controller.app
        app.opts.dry_run = False
        fsc = app.controllers.Filesystem
        fsc.reset_partition_only = True
        app.package_installer = Mock()
        app.command_runner = AsyncMock()
        self.run = app.command_runner.run = AsyncMock(
            return_value=subprocess.CompletedProcess((), 0, stdout=lsblk_output)
        )
        app.package_installer.install_pkg = AsyncMock()
        app.package_installer.install_pkg.return_value = PackageInstallState.DONE
        fsm, self.part = make_model_and_partition()

    async def test_configure_rp_boot_grub(self):
        fsuuid, partuuid = "fsuuid", "partuuid"
        self.setup_rp_test(f"{fsuuid}\t{partuuid}".encode("ascii"))
        await self.controller.configure_rp_boot_grub(rp=self.part)
        with open(self.controller.tpath("etc/grub.d/99_reset")) as fp:
            cfg = fp.read()
        self.assertIn("--fs-uuid fsuuid", cfg)

    @patch("subiquity.server.controllers.install.run_curtin_command")
    @patch(
        "subiquity.server.controllers.install.get_users_and_groups",
        Mock(return_value=["admin", "sudo"]),
    )
    async def test_create_users(self, run_curtin_cmd):
        self.controller.model = Mock()
        self.controller.tpath = Mock(return_value="/tmp/foo")
        with patch.object(
            self.controller.model.identity,
            "user",
            User(
                username="user",
                password="$6$xxx12345",
                realname="my user",
                groups={DefaultGroups},
            ),
        ):
            await self.controller.create_users(Mock())
        expected_useradd = [
            "useradd",
            "user",
            "--comment",
            "my user",
            "--shell",
            "/bin/bash",
            "--groups",
            "admin,sudo",
            "--create-home",
        ]
        expected_chpasswd = ["chpasswd", "--encrypted"]

        expected_calls = [
            call(
                ANY,
                ANY,
                "in-target",
                "-t",
                ANY,
                "--",
                *expected_useradd,
                private_mounts=False,
            ),
            call(
                ANY,
                ANY,
                "in-target",
                "-t",
                ANY,
                "--",
                *expected_chpasswd,
                private_mounts=False,
                input=b"user:$6$xxx12345",
                capture=True,
            ),
        ]
        self.assertEqual(expected_calls, run_curtin_cmd.mock_calls)

    @patch("subiquity.server.controllers.install.run_curtin_command")
    async def test_create_users_no_identity(self, run_curtin_cmd):
        self.controller.model = Mock()
        with patch.object(self.controller.model.identity, "user", None):
            await self.controller.create_users(Mock())

        run_curtin_cmd.assert_not_called()

    @patch("platform.machine", return_value="s390x")
    @patch("subiquity.server.controllers.install.arun_command")
    async def test_postinstall_platform_s390x(self, arun, machine):
        await self.controller.platform_postinstall()
        arun.assert_called_once_with(["chreipl", "/target/boot"])

    @patch("platform.machine", return_value="s390x")
    async def test_postinstall_platform_s390x_fail(self, machine):
        cpe = subprocess.CalledProcessError(
            cmd=["chreipl", "/target/boot"],
            returncode=1,
            stderr="chreipl: No valid target specified",
        )

        arun_patch = patch(
            "subiquity.server.controllers.install.arun_command", side_effect=cpe
        )

        assert_logs = self.assertLogs(
            "subiquity.server.controllers.install", level="WARNING"
        )
        assert_raises = self.assertRaises(subprocess.CalledProcessError)

        with assert_logs as errors, assert_raises, arun_patch as arun:
            await self.controller.platform_postinstall()

        arun.assert_called_once_with(["chreipl", "/target/boot"])
        self.assertIn(
            ("chreipl stderr:\n%s", ["chreipl: No valid target specified"]),
            [(record.msg, list(record.args)) for record in errors.records],
        )

    @patch("platform.machine", return_value="amd64")
    @patch("subiquity.server.controllers.install.arun_command")
    async def test_postinstall_platform_amd64(self, arun, machine):
        await self.controller.platform_postinstall()
        arun.assert_not_called()

    async def test_write_autoinstall_config(self):
        self.controller.write_autoinstall_config()
        user_data = (
            self.controller.app.root + "/var/log/installer/autoinstall-user-data"
        )
        with open(user_data) as file:
            data = file.read()
            self.assertIn(
                "https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html",  # noqa: E501
                data,
            )

    def test_error_in_curtin_invocation(self):
        method = self.controller.error_in_curtin_invocation

        self.assertIsNone(method(Exception()))
        self.assertIsNone(method(RuntimeError()))

        self.assertIsNone(method(CurtinInstallError(stages=[])))
        # Running multiple stages in one "curtin step" is not something that
        # currently happens in practice.
        self.assertIsNone(
            method(CurtinInstallError(stages=["extract", "partitioning"]))
        )

        self.assertEqual("extract", method(CurtinInstallError(stages=["extract"])))
        self.assertEqual("curthooks", method(CurtinInstallError(stages=["curthooks"])))

    async def test_adjust_rp(self):
        orig_casper_uuid = str(uuid.uuid4())
        partuuid = str(uuid.uuid4())

        with tempfile.TemporaryDirectory() as tempdir:
            d = Path(tempdir)

            (d / "boot/grub").mkdir(parents=True)
            orig_grub_conf = f"""\
menuentry "Restore Ubuntu to factory state" {{
	set gfxpayload=keep
	linux	/casper/vmlinuz layerfs-path=minimal.standard.live.squashfs nopersistent ds=nocloud\\;s=/cdrom/cloud-configs/reset-media uuid={orig_casper_uuid} --- quiet splash
	initrd	/casper/initrd
}}
"""  # noqa
            (d / "boot/grub/grub.cfg").write_text(orig_grub_conf)

            (d / ".disk").mkdir()
            (d / ".disk/casper-uuid-generic").write_text(orig_casper_uuid)

            mp = Mountpoint(mountpoint=tempdir)
            self.setup_rp_test(f"{partuuid}".encode("ascii"))
            new_casper_uuid = await self.controller.adjust_rp(self.part, mp)
            try:
                uuid.UUID(new_casper_uuid)
            except ValueError:
                self.fail("adjust_rp should return a valid uuid for casper uuid")

            ref_grub_conf = f"""\
menuentry "Restore Ubuntu to factory state" {{
	set gfxpayload=keep
linux /casper/vmlinuz layerfs-path=minimal.standard.live.squashfs nopersistent 'ds=nocloud;s=/cdrom/cloud-configs/reset-media' uuid={new_casper_uuid} rp-partuuid={partuuid} --- quiet splash
	initrd	/casper/initrd
}}
"""  # noqa
            grub_conf_from_file = (d / "boot/grub/grub.cfg").read_text()
            self.assertEqual(ref_grub_conf, grub_conf_from_file)
            casper_uuid_from_file = (
                (d / ".disk/casper-uuid-generic").read_text().strip()
            )
            self.assertEqual(new_casper_uuid, casper_uuid_from_file)


class TestInstallControllerDriverMatch(unittest.TestCase):
    def setUp(self):
        self.ic = InstallController(make_app())

    @parameterized.expand(
        (
            # no components
            ([], ["nvidia-driver-510"], []),
            # no drivers detected
            (["nvidia-510-uda-ko", "nvidia-510-uda-user"], [], []),
            # missing user component
            (["nvidia-510-uda-ko"], ["nvidia-driver-510"], []),
            # missing ko component
            (["nvidia-510-uda-user"], ["nvidia-driver-510"], []),
            # mismatched component versions, nothing usable available
            (
                ["nvidia-2-uda-ko", "nvidia-1-uda-user"],
                ["nvidia-driver-999"],
                [],
            ),
            # match
            (
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
                ["nvidia-driver-510"],
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            ),
            # match, open driver
            (
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
                ["nvidia-driver-510-open"],
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            ),
            # match, server driver
            (
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
                ["nvidia-driver-510-server"],
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            ),
            # match, open server driver
            (
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
                ["nvidia-driver-510-server-open"],
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            ),
            # match, open server driver, erd
            (
                ["nvidia-510-erd-ko", "nvidia-510-erd-user"],
                ["nvidia-driver-510-server-open"],
                ["nvidia-510-erd-ko", "nvidia-510-erd-user"],
            ),
            # prefer "newer" based on a reversed sort
            (
                [
                    "nvidia-1-uda-ko",
                    "nvidia-1-uda-user",
                    "nvidia-2-uda-ko",
                    "nvidia-2-uda-user",
                ],
                ["nvidia-driver-1", "nvidia-driver-2"],
                ["nvidia-2-uda-ko", "nvidia-2-uda-user"],
            ),
            (
                [
                    "nvidia-1-uda-ko",
                    "nvidia-1-uda-user",
                    "nvidia-2-uda-ko",
                    "nvidia-2-uda-user",
                ],
                ["nvidia-driver-2", "nvidia-driver-1"],
                ["nvidia-2-uda-ko", "nvidia-2-uda-user"],
            ),
            # wrong driver version
            (
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
                ["nvidia-driver-999"],
                ["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            ),
            # wrong driver version, erd
            (
                ["nvidia-510-erd-ko", "nvidia-510-erd-user"],
                ["nvidia-driver-999"],
                ["nvidia-510-erd-ko", "nvidia-510-erd-user"],
            ),
            # wrong driver version, use newer
            (
                [
                    "nvidia-1-uda-ko",
                    "nvidia-2-uda-user",
                    "nvidia-2-uda-ko",
                    "nvidia-1-uda-user",
                ],
                ["nvidia-driver-999"],
                ["nvidia-2-uda-ko", "nvidia-2-uda-user"],
            ),
            # mismatched component versions, something usable available
            (
                ["nvidia-1-uda-ko", "nvidia-2-uda-ko", "nvidia-1-uda-user"],
                ["nvidia-driver-999"],
                ["nvidia-1-uda-ko", "nvidia-1-uda-user"],
            ),
            # branch mismatch
            (
                ["nvidia-1-uda-ko", "nvidia-1-erd-user"],
                ["nvidia-driver-999"],
                [],
            ),
        )
    )
    def test_kernel_components(self, comps, drivers, expected):
        self.ic.app.controllers.Filesystem._info.available_kernel_components = comps
        self.ic.app.controllers.Drivers.drivers = drivers
        self.assertEqual(expected, self.ic.kernel_components())
