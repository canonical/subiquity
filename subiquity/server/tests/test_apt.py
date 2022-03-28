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
from subiquitycore.tests.util import run_coro
from subiquity.server.apt import (
    AptConfigurer,
    Mountpoint,
    OverlayMountpoint,
    lowerdir_for,
)
from subiquity.models.mirror import MirrorModel, DEFAULT
from subiquity.models.proxy import ProxyModel


class TestAptConfigurer(SubiTestCase):
    def setUp(self):
        self.base_config = {'apt': DEFAULT}
        self.base_config['apt']['disable_components'] = []

        self.model = Mock()
        self.model.mirror = MirrorModel()
        self.model.proxy = ProxyModel()
        self.app = make_app(self.model)
        self.configurer = AptConfigurer(self.app, '')

    def test_apt_config_noproxy(self):
        expected = self.base_config
        self.assertEqual(expected, self.configurer.apt_config())

    def test_apt_config_proxy(self):
        proxy = 'http://apt-cacher-ng:3142'
        self.model.proxy.proxy = proxy
        expected = self.base_config
        expected['apt']['http_proxy'] = proxy
        expected['apt']['https_proxy'] = proxy
        self.assertEqual(expected, self.configurer.apt_config())

    def test_mount_unmount(self):
        # Make sure we can unmount something that we mounted before.
        with patch.object(self.app, "command_runner",
                          create=True, new_callable=AsyncMock):
            m = run_coro(self.configurer.mount("/dev/cdrom", "/target"))
            run_coro(self.configurer.unmount(m))

    def test_overlay(self):
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

        async def coro():
            async with self.configurer.overlay():
                pass

        with patch.object(self.app, "command_runner",
                          create=True, new_callable=AsyncMock):
            run_coro(coro())


class TestLowerDirFor(SubiTestCase):
    def test_lowerdir_for_str(self):
        self.assertEqual(
                lowerdir_for("/tmp/lower1"),
                "/tmp/lower1")

    def test_lowerdir_for_str_list(self):
        self.assertEqual(
                lowerdir_for(["/tmp/lower1", "/tmp/lower2"]),
                "/tmp/lower2:/tmp/lower1")

    def test_lowerdir_for_mountpoint(self):
        self.assertEqual(
                lowerdir_for(Mountpoint(mountpoint="/mnt")),
                "/mnt")

    def test_lowerdir_for_simple_overlay(self):
        overlay = OverlayMountpoint(
                lowers=["/tmp/lower1"],
                upperdir="/tmp/upper1",
                mountpoint="/mnt",
        )
        self.assertEqual(lowerdir_for(overlay), "/tmp/upper1:/tmp/lower1")

    def test_lowerdir_for_overlay(self):
        overlay = OverlayMountpoint(
                lowers=["/tmp/lower1", "/tmp/lower2"],
                upperdir="/tmp/upper1",
                mountpoint="/mnt",
        )
        self.assertEqual(
                lowerdir_for(overlay),
                "/tmp/upper1:/tmp/lower2:/tmp/lower1")

    def test_lowerdir_for_list(self):
        overlay = OverlayMountpoint(
                lowers=["/tmp/overlaylower1", "/tmp/overlaylower2"],
                upperdir="/tmp/overlayupper1",
                mountpoint="/mnt/overlay",
        )
        mountpoint = Mountpoint(mountpoint="/mnt/mountpoint")
        lowers = ["/tmp/lower1", "/tmp/lower2"]
        self.assertEqual(
                lowerdir_for([overlay, mountpoint, lowers]),
                "/tmp/lower2:/tmp/lower1" +
                ":/mnt/mountpoint" +
                ":/tmp/overlayupper1:/tmp/overlaylower2:/tmp/overlaylower1")

    def test_lowerdir_for_other(self):
        with self.assertRaises(NotImplementedError):
            lowerdir_for(None)

        with self.assertRaises(NotImplementedError):
            lowerdir_for(10)
