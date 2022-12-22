# Copyright 2021 Canonical, Ltd.
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

from unittest.mock import Mock, patch, AsyncMock

from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquity.server.apt import (
    AptConfigurer,
    OverlayMountpoint,
)
from subiquity.models.mirror import MirrorModel
from subiquity.models.proxy import ProxyModel


class TestAptConfigurer(SubiTestCase):
    def setUp(self):
        self.model = Mock()
        self.model.mirror = MirrorModel()
        self.model.proxy = ProxyModel()
        self.app = make_app(self.model)
        self.configurer = AptConfigurer(self.app, AsyncMock(), '')

    def test_apt_config_noproxy(self):
        config = self.configurer.apt_config()
        self.assertNotIn("http_proxy", config["apt"])
        self.assertNotIn("https_proxy", config["apt"])

    def test_apt_config_proxy(self):
        proxy = 'http://apt-cacher-ng:3142'
        self.model.proxy.proxy = proxy

        config = self.configurer.apt_config()
        self.assertEqual(proxy, config["apt"]["http_proxy"])
        self.assertEqual(proxy, config["apt"]["https_proxy"])

    async def test_overlay(self):
        self.configurer.install_tree = OverlayMountpoint(
                upperdir="upperdir-install-tree",
                lowers=["lowers1-install-tree"],
                mountpoint="mountpoint-install-tree",
                )
        self.configurer.configured_tree = OverlayMountpoint(
                upperdir="upperdir-install-tree",
                lowers=["lowers1-install-tree"],
                mountpoint="mountpoint-install-tree",
                )
        self.source = "source"

        with patch.object(self.app, "command_runner",
                          create=True, new_callable=AsyncMock):
            async with self.configurer.overlay():
                pass
