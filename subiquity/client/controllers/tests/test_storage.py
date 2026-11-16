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

from unittest.mock import AsyncMock, patch

from subiquity.client.controllers.storage import StorageController
from subiquity.common.types.storage import (
    GuidedCapability,
    GuidedChoiceV2,
    GuidedStorageTargetManual,
    ProbeStatus,
    StorageResponse,
)
from subiquity.models.storage import FirmwareType, StorageModel
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app


async def _passthrough(awaitable):
    return await awaitable


class TestStorageControllerProbing(SubiTestCase):
    """The server can be in the middle of a probert run (e.g., restarted by a
    udev event) when the client asks for the storage config. The client must
    not try to load a PROBING response, which has no config.
    LP: #2174522"""

    def setUp(self):
        self.app = make_app()
        self.app.client = AsyncMock()
        self.app.wait_with_progress = _passthrough
        self.controller = StorageController(self.app)
        self.controller.supports_nvme_tcp_booting = False

        # Behave like the server while a probe is running: GET /storage
        # returns PROBING (and config=None), unless the client waits for the
        # probe to finish or asks for the cached result.
        async def storage_GET(wait=False, use_cached_result=False):
            if wait or use_cached_result:
                return StorageResponse(
                    status=ProbeStatus.DONE,
                    firmware_type=FirmwareType.UEFI,
                    orig_config=[],
                    config=[],
                    dasd={},
                )
            return StorageResponse(status=ProbeStatus.PROBING)

        self.controller.endpoint.GET = AsyncMock(side_effect=storage_GET)

    async def test_guided_choice_manual_while_probing(self):
        choice = GuidedChoiceV2(
            target=GuidedStorageTargetManual(),
            capability=GuidedCapability.MANUAL,
        )
        with (
            patch("subiquity.client.controllers.storage.StorageView") as view,
            patch("subiquity.client.controllers.storage.read_ubuntu_info") as info,
        ):
            info.return_value.version_number.return_value = (26, 4)
            await self.controller._guided_choice(choice)

        self.controller.endpoint.v2.guided.POST.assert_awaited_once_with(choice)
        view.assert_called_once_with(self.controller.model, self.controller)

    async def test_reset_while_probing(self):
        self.controller.model = StorageModel(FirmwareType.UEFI, root="/", dry_run=True)
        with patch("subiquity.client.controllers.storage.StorageView") as view:
            await self.controller._reset(refresh_view=True)

        self.controller.endpoint.v2.reset.POST.assert_awaited_once_with()
        view.assert_called_once_with(self.controller.model, self.controller)
