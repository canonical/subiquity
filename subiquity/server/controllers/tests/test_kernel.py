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
import os.path

from subiquity.models.kernel import KernelModel
from subiquity.server.controllers.kernel import KernelController
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


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
        self.assertEqual("linux-generic", self.controller.model.metapkg_name)

    def test_mpfile_run(self):
        self.setup_mpfile("run", "linux-aaaa")
        self.controller.start()
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
            [None, None, "linux-generic"],
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
