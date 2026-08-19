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

from pathlib import Path
from unittest import IsolatedAsyncioTestCase, mock

from subiquity.server.controllers.storage import VariationInfo
from subiquity.server.snapd import api as snapdapi
from subiquity.server.snapd import types as snapdtypes
from subiquity.server.snapd.core_boot_installer import (
    CoreBootInstaller,
    CoreBootInstallPlan,
)
from subiquitycore.snapd import AsyncSnapd, get_fake_connection
from subiquitycore.tests.mocks import make_app


class TestCoreBootInstaller(IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = make_app()

    async def test_setup_encryption__passes_keyboard_config(self):
        info = mock.Mock()
        info.label = "prefer-encrypted"
        info.system.volumes = {"vol-key": mock.Mock()}
        plan = CoreBootInstallPlan(
            info=info,
            on_volume=mock.Mock(),
            volumes_auth=None,
        )

        kb = self.app.base_model.keyboard
        kb.setting.layout = "fr"
        kb.setting.variant = "azerty"
        kb.setting.toggle = "alt_shift_toggle"

        with mock.patch.object(
            snapdapi,
            "post_and_wait",
            return_value=mock.Mock(encrypted_devices={}),
        ) as m_post:
            installer = CoreBootInstaller(self.app, plan)
            await installer.setup_encryption(
                context=mock.MagicMock(),
                apply_encrypted_devices=mock.Mock(),
            )

        # post_and_wait is called as:
        #   post_and_wait(client, meth, request, ann=...)
        # so:
        #   args[0] is the snapdapi client
        #   args[1] is the systems[label].POST bound method
        #   args[2] is the SystemActionRequest
        req = m_post.call_args.args[2]
        self.assertEqual(
            snapdtypes.KeyboardConfig(
                model="pc105",
                layout="fr",
                variant="azerty",
                options=["grp:alt_shift_toggle"],
            ),
            req.keyboard_config,
        )

    async def test_fetch_core_boot_recovery_key(self):
        self.app.snapd = AsyncSnapd(get_fake_connection())
        self.app.snapdapi = snapdapi.make_api_client(self.app.snapd)
        info = mock.Mock(label="my-label")
        plan = CoreBootInstallPlan(
            info=info,
            on_volume=None,
            volumes_auth=None,
        )

        m_set_key = mock.Mock()
        installer = CoreBootInstaller(self.app, plan)
        key = await installer.fetch_core_boot_recovery_key()
        m_set_key(key)

        m_set_key.assert_called_once_with("my-recovery-key")

    @mock.patch("subiquity.server.mounter.Mounter.bind_mounted")
    @mock.patch.object(Path, "mkdir", mock.Mock())
    async def test_target_preseed(self, m_bind_mounted):
        info = mock.Mock(label="mock-label")
        plan = CoreBootInstallPlan(
            info=info,
            on_volume=None,
            volumes_auth=None,
        )

        with mock.patch.object(snapdapi, "post_and_wait") as mock_post:
            installer = CoreBootInstaller(self.app, plan)
            await installer.target_preseed(Path("/target"))

        expected_mounted_calls = [
            mock.call(Path("/dev"), Path("/target/dev")),
            mock.call(Path("/proc"), Path("/target/proc")),
            mock.call(Path("/sys"), Path("/target/sys")),
            mock.call(
                Path("/sys/kernel/security"), Path("/target/sys/kernel/security")
            ),
            mock.call(Path("/var/lib/snapd/seed"), Path("/target/var/lib/snapd/seed")),
        ]

        self.assertEqual(expected_mounted_calls, m_bind_mounted.call_args_list)

        mock_post.assert_called_once()

    async def test_finish_install(self):
        self.app.snapdapi = snapdapi.make_api_client(AsyncSnapd(get_fake_connection()))
        variation_info = VariationInfo(
            name="mock",
            label="mock-label",
            system=snapdtypes.SystemDetails(
                label="mock-label",
                volumes={
                    "mockVol": snapdtypes.Volume(
                        schema="mock", structure=None, bootloader="grub"
                    ),
                },
                model=snapdtypes.Model(
                    architecture="mock-arch",
                    snaps=[
                        snapdtypes.ModelSnap(
                            name="MockKernel",
                            type=snapdtypes.ModelSnapType.KERNEL,
                            presence=snapdtypes.PresenceValue.REQUIRED,
                            components={
                                "nvidia-510-uda-ko": snapdtypes.PresenceValue.OPTIONAL,
                                "nvidia-510-uda-user": snapdtypes.PresenceValue.OPTIONAL,
                                "foo": snapdtypes.PresenceValue.OPTIONAL,
                                "bar": snapdtypes.PresenceValue.OPTIONAL,
                            },
                            default_channel="foo",
                            id="bar",
                        ),
                        snapdtypes.ModelSnap(
                            name="MockApp1",
                            type=snapdtypes.ModelSnapType.APP,
                            presence=snapdtypes.PresenceValue.REQUIRED,
                            default_channel="foo",
                            id="bar",
                        ),
                        snapdtypes.ModelSnap(
                            name="MockApp2",
                            type=snapdtypes.ModelSnapType.APP,
                            presence=snapdtypes.PresenceValue.OPTIONAL,
                            default_channel="foo",
                            id="bar",
                        ),
                    ],
                ),
                available_optional=snapdtypes.AvailableOptional(
                    snaps=["MockApp2"],
                    components={
                        "MockKernel": [
                            "nvidia-510-uda-ko",
                            "nvidia-510-uda-user",
                            "foo",
                            "bar",
                        ]
                    },
                ),
            ),
        )
        plan = CoreBootInstallPlan(
            info=variation_info,
            on_volume=None,
            volumes_auth=None,
        )
        with mock.patch.object(snapdapi, "post_and_wait") as mock_post:
            installer = CoreBootInstaller(self.app, plan)
            await installer.finish_install(
                context=mock.MagicMock(),
                kernel_components=["nvidia-510-uda-ko", "nvidia-510-uda-user"],
            )
        mock_post.assert_called_once()

        # Assert installing all optional snaps but only the requested components
        expected_optional_install = snapdtypes.OptionalInstall(
            all=False,
            components={"MockKernel": ["nvidia-510-uda-ko", "nvidia-510-uda-user"]},
            snaps=variation_info.system.available_optional.snaps,
        )
        actual = mock_post.call_args.args[2].optional_install

        self.assertEqual(expected_optional_install, actual)
