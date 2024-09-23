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

import itertools
import os
import os.path

import attr

from subiquity.models.kernel import KernelModel
from subiquity.models.source import BridgeKernelReason, SourceModel
from subiquity.server.controllers.kernel import KernelController
from subiquity.server.types import InstallerChannels
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


@attr.s(auto_attribs=True)
class BridgeTestScenario:
    bridge_reasons: list[BridgeKernelReason]
    detected_reasons: list[BridgeKernelReason]
    search_drivers: bool
    drivers_do_install: bool
    use_bridge: bool


def n_booleans(*, n):
    return itertools.product(*(((True, False),) * n))


bridge_scenarios = []
for bridge_zfs, bridge_nvidia, has_zfs, has_nvidia in n_booleans(n=4):
    # We consider scenarios for each reason being a reason to choose
    # the kernel and actually discovered.
    bridge_reasons = []
    if bridge_zfs:
        bridge_reasons.append(BridgeKernelReason.ZFS)
    if bridge_nvidia:
        bridge_reasons.append(BridgeKernelReason.NVIDIA)
    detected_reasons = []
    if has_zfs:
        detected_reasons.append(BridgeKernelReason.ZFS)
    if has_nvidia:
        detected_reasons.append(BridgeKernelReason.NVIDIA)
    for search_drivers, do_install in n_booleans(n=2):
        # Then we consider scenarios where the user chooses whether or
        # not to search for drivers and whether or not to install the
        # drivers
        if not search_drivers and do_install:
            continue
        use_bridge = False
        if bridge_zfs and has_zfs:
            use_bridge = True
        if bridge_nvidia and has_nvidia and do_install:
            use_bridge = True
        bridge_scenarios.append(
            (
                BridgeTestScenario(
                    bridge_reasons=bridge_reasons,
                    detected_reasons=detected_reasons,
                    search_drivers=search_drivers,
                    drivers_do_install=do_install,
                    use_bridge=use_bridge,
                ),
            )
        )


class TestMetapackageSelection(SubiTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.base_model.root = self.tmp_dir()
        self.controller = KernelController(app=self.app)
        self.controller.model = KernelModel()

    def setup_mpfile(self, dirpath, data):
        runfile = self.tmp_path(
            f"{dirpath}/kernel-meta-package", dir=self.app.base_model.root
        )
        os.makedirs(os.path.dirname(runfile), exist_ok=True)
        with open(runfile, "w") as fp:
            fp.write(data)

    def test_defaults(self):
        self.controller.start()
        self.assertEqual(None, self.controller.model.metapkg_name)

    async def test_defaults_from_source(self):
        self.app.base_model.source.catalog.kernel.default = "default-kernel"
        self.controller.start()
        await self.app.hub.abroadcast((InstallerChannels.CONFIGURED, "source"))
        self.assertEqual("default-kernel", self.controller.model.metapkg_name)

    def test_mpfile_run(self):
        self.setup_mpfile("run", "linux-aaaa")
        self.controller.start()
        self.assertEqual("linux-aaaa", self.controller.model.metapkg_name)

    async def test_mpfile_run_overrides_source(self):
        self.app.base_model.source.catalog.kernel.default = "default-kernel"
        self.setup_mpfile("run", "linux-aaaa")
        self.controller.start()
        await self.app.hub.abroadcast((InstallerChannels.CONFIGURED, "source"))
        self.assertEqual("linux-aaaa", self.controller.model.metapkg_name)

    def test_mpfile_etc(self):
        self.setup_mpfile("etc/subiquity", "linux-zzzz")
        self.controller.start()
        self.assertEqual("linux-zzzz", self.controller.model.metapkg_name)

    def test_mpfile_both(self):
        self.setup_mpfile("run", "linux-aaaa")
        self.setup_mpfile("etc/subiquity", "linux-zzzz")
        self.controller.start()
        self.assertEqual("linux-aaaa", self.controller.model.metapkg_name)

    @parameterized.expand(
        [
            [None, None, None],
            [None, {}, "linux-generic"],
            # when the metapackage file is set, it should be used.
            ["linux-zzzz", None, "linux-zzzz"],
            # when we have a metapackage file and autoinstall, use autoinstall.
            ["linux-zzzz", {"package": "linux-aaaa"}, "linux-aaaa"],
            [None, {"package": "linux-aaaa"}, "linux-aaaa"],
            [None, {"package": "linux-aaaa", "flavor": "bbbb"}, "linux-aaaa"],
            [None, {"flavor": None}, "linux-generic"],
            [None, {"flavor": "generic"}, "linux-generic"],
            [None, {"flavor": "hwe"}, "linux-generic-hwe-20.04"],
            [None, {"flavor": "bbbb"}, "linux-bbbb-20.04"],
        ]
    )
    def test_ai(self, mpfile_data, ai_data, metapkg_name):
        if mpfile_data is not None:
            self.setup_mpfile("etc/subiquity", mpfile_data)
        self.controller.load_autoinstall_data(ai_data)
        self.controller.start()
        self.assertEqual(metapkg_name, self.controller.model.metapkg_name)

    @parameterized.expand(bridge_scenarios)
    async def test_bridge_options(self, scenario):
        # This test "knows" a bit too much about which conditions the
        # bridge kernel code uses to check for the various
        # reasons. But its better than no tests.
        source_model = self.app.base_model.source = SourceModel()
        source_model.catalog.kernel.default = "linux-default"
        source_model.catalog.kernel.bridge = "linux-bridge"
        source_model.catalog.kernel.bridge_reasons = scenario.bridge_reasons
        source_model.search_drivers = scenario.search_drivers

        self.controller.start()

        await self.app.hub.abroadcast((InstallerChannels.CONFIGURED, "source"))

        if BridgeKernelReason.ZFS in scenario.detected_reasons:
            self.app.base_model.filesystem.uses_zfs.return_value = True
        else:
            self.app.base_model.filesystem.uses_zfs.return_value = False

        await self.app.hub.abroadcast(InstallerChannels.INSTALL_CONFIRMED)

        if not scenario.search_drivers:
            drivers = []
        elif BridgeKernelReason.NVIDIA in scenario.detected_reasons:
            drivers = ["something-else", "nvidia-driver"]
        else:
            drivers = ["something-else"]
        self.app.controllers.Drivers.model.do_install = scenario.drivers_do_install
        self.app.controllers.Drivers.drivers = drivers
        await self.app.hub.abroadcast(InstallerChannels.DRIVERS_DECIDED)

        if scenario.use_bridge:
            self.assertEqual("linux-bridge", self.controller.model.metapkg_name)
        else:
            self.assertEqual("linux-default", self.controller.model.metapkg_name)
