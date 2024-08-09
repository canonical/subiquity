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

from subiquity.models.kernel import KernelModel
from subiquitycore.tests import SubiTestCase


class TestKernelModel(SubiTestCase):
    def setUp(self):
        self.model = KernelModel()

    def testInstall(self):
        kernel = "kernel-a"
        self.model.metapkg_name = kernel
        expected = {
            "kernel": {
                "package": "kernel-a",
                "remove_existing": True,
            }
        }

        self.assertEqual(expected, self.model.render())

    def testNoInstall(self):
        kernel = "kernel-a"
        self.model.metapkg_name = kernel
        self.model.curthooks_install = False
        expected = {
            "kernel": {
                "install": False,
                "remove_existing": True,
            }
        }

        self.assertEqual(expected, self.model.render())

    def testNoInstallRemoveGeneric(self):
        kernel = "kernel-a"
        self.model.metapkg_name = kernel
        self.model.curthooks_install = False
        self.model.remove = [kernel]
        expected = {
            "kernel": {
                "install": False,
                "remove": [kernel],
            }
        }

        self.assertEqual(expected, self.model.render())

    def testInstallAndRemove(self):
        install_kernel = "kernel-a"
        remove_kernel = "kernel-b"
        self.model.metapkg_name = install_kernel
        self.model.remove = [remove_kernel]
        expected = {
            "kernel": {
                "package": install_kernel,
                "remove": [remove_kernel],
            }
        }

        self.assertEqual(expected, self.model.render())
