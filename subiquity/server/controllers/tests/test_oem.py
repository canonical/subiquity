# Copyright 2023 Canonical, Ltd.
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

import subprocess
from unittest.mock import Mock, patch

import jsonschema
from jsonschema.validators import validator_for

from subiquity.server.controllers.oem import OEMController
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app


class TestOEMController(SubiTestCase):
    def setUp(self):
        with patch("subiquity.server.controllers.oem.get_ubuntu_drivers_interface"):
            self.controller = OEMController(make_app())

    async def test_wants_oem_kernel_default(self):
        apt_cache_show_output = b"""\
Package: oem-somerville-tentacool-meta
Architecture: all
Version: 22.04~ubuntu1
Priority: optional
Section: misc
Origin: Ubuntu
Maintainer: Commercial Engineering <commercial-engineering@canonical.com>
Bugs: https://bugs.launchpad.net/ubuntu/+filebug
Installed-Size: 14
Depends: ubuntu-oem-keyring
Filename: pool/main/o/oem-somerville-tentacool-meta/\
oem-somerville-tentacool-meta_22.04~ubuntu1_all.deb
Size: 1966
MD5sum: 54c21fc5081342a1cf2713bf5337c7fe
SHA1: 0503bf47dc27fc7e1228c8bbbbfcf217cace4d20
SHA256: 06832f9d0e20c14e46f0666f551777cce94eff9fe01ca6e171c1ce36c344be39
SHA512: 09399fb7d08f692ed93f714b382e9686072c270382af9f0a0753c5f6da3c3089\
0d37bf15a7493f4256a1a0a27be0635a5f9d6dd52478be02a8754ae040f4d08f
Description-en: hardware support for Dell XPS 13 9320
 This is a metapackage for Dell PC:
  * Dell XPS 13 9320
 It installs packages needed to support this hardware fully.
Description-md5: 1224924b830bd467ae43de5de655ed76
Modaliases: meta(pci:*sv00001028sd00000AF3bc0Csc05*)
Ubuntu-Oem-Kernel-Flavour: default
"""
        subprocess_return = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=apt_cache_show_output
        )

        with patch(
            "subiquity.server.controllers.oem.run_curtin_command",
            return_value=subprocess_return,
        ):
            self.assertFalse(
                await self.controller.wants_oem_kernel(
                    "oem-somerville-tentacool-meta", context=None, overlay=Mock()
                )
            )

    async def test_wants_oem_kernel_oem(self):
        apt_cache_show_output = b"""\
Package: oem-sutton-balint-meta
Architecture: all
Version: 22.04~ubuntu1
Priority: optional
Section: misc
Origin: Ubuntu
Maintainer: Commercial Engineering <commercial-engineering@canonical.com>
Bugs: https://bugs.launchpad.net/ubuntu/+filebug
Installed-Size: 13
Depends: ubuntu-oem-keyring
Filename: pool/main/o/oem-sutton-balint-meta/\
oem-sutton-balint-meta_22.04~ubuntu1_all.deb
Size: 1906
MD5sum: c05aba72ecdb44cadba5443fdcc81ae9
SHA1: f35dcdc8d245252d4d298a9ed07620fa37f0dede
SHA256: 5d5b08b2bfed3e34548db23b40a363b6fa819a9e0d9e1ffe96e067a56bbb813a
SHA512: d207624a58b38aad165b35401615ab2a4d4184264fec4e9735c7dfcd6b4ee727\
aa95bc41394c7a3fda0006ae0a00ef7cab474e42724b94a596f493b1f563f097
Description-en: hardware support for Lenovo ThinkPad P16 Gen 1
 This is a metapackage for Lenovo PC:
  * Lenovo ThinkPad P16 Gen 1
 It installs packages needed to support this hardware fully.
Description-md5: 3963562d6f85b81c4b21e6a7bff3a2c4
Modaliases: meta(dmi:*bvnLENOVO:bvrN3F*:pvrThinkPad*)
Ubuntu-Oem-Kernel-Flavour: oem
"""

        subprocess_return = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=apt_cache_show_output
        )

        with patch(
            "subiquity.server.controllers.oem.run_curtin_command",
            return_value=subprocess_return,
        ):
            self.assertTrue(
                await self.controller.wants_oem_kernel(
                    "oem-sutton-balint-meta", context=None, overlay=Mock()
                )
            )

    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            OEMController.autoinstall_schema
        )

        JsonValidator.check_schema(OEMController.autoinstall_schema)
