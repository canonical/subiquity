# Copyright 2024 Canonical, Ltd.
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

import asyncio
from unittest import IsolatedAsyncioTestCase, mock

import jsonschema
from jsonschema.validators import validator_for

from subiquity.server.controllers.proxy import ProxyController
from subiquity.server.types import InstallerChannels
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app


class TestProxyController(SubiTestCase):
    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            ProxyController.autoinstall_schema
        )

        JsonValidator.check_schema(ProxyController.autoinstall_schema)


class TestProxyPost(IsolatedAsyncioTestCase):
    async def test_POST_waits_for_restart(self):
        app = make_app()
        release = asyncio.Event()

        async def on_proxy():
            await release.wait()

        app.hub.subscribe(InstallerChannels.NETWORK_PROXY_SET, on_proxy)
        ctrl = ProxyController(app)
        with mock.patch.object(ctrl, "configured", new=mock.AsyncMock()):
            post = asyncio.create_task(ctrl.POST("http://proxy.example:3128"))
            await asyncio.sleep(0)
            self.assertFalse(post.done())
            release.set()
            await post

        self.assertEqual("http://proxy.example:3128", ctrl.model.proxy)
