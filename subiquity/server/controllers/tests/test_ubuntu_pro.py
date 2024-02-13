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

from unittest import mock

import jsonschema
from jsonschema.validators import validator_for

from subiquity.server.controllers.ubuntu_pro import UbuntuProController
from subiquity.server.dryrun import DRConfig
from subiquitycore.lsb_release import lsb_release_from_path
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


class TestUbuntuProController(SubiTestCase):
    def setUp(self):
        app = make_app()
        app.dr_cfg = DRConfig()
        self.controller = UbuntuProController(app)

    def test_serialize(self):
        self.controller.model.token = "1a2b3C"
        self.assertEqual(self.controller.serialize(), "1a2b3C")

    def test_deserialize(self):
        self.controller.deserialize("1A2B3C4D")
        self.assertEqual(self.controller.model.token, "1A2B3C4D")

    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            UbuntuProController.autoinstall_schema
        )

        JsonValidator.check_schema(UbuntuProController.autoinstall_schema)

    @parameterized.expand(
        [
            ("focal", 23000, 2300, 2030),
            ("impish", 23000, 2300, None),
            ("jammy", 23000, 2300, 2032),
            ("noble", 23000, 2300, 2034),
        ]
    )
    async def test_info_GET__series(
        self, series: str, universe_pkgs: int, main_pkgs: int, esm_eol_year: int | None
    ):
        def fake_lsb_release(*args, **kwargs):
            return lsb_release_from_path(f"examples/lsb-release-{series}")

        with mock.patch(
            "subiquity.server.controllers.ubuntu_pro.lsb_release",
            wraps=fake_lsb_release,
        ) as m_lsb_release:
            info = await self.controller.info_GET()

        m_lsb_release.assert_called_once()

        self.assertEqual(universe_pkgs, info.universe_packages)
        self.assertEqual(main_pkgs, info.main_packages)
        if esm_eol_year is not None:
            self.assertEqual(esm_eol_year, info.eol_esm_year)
        else:
            self.assertIsNone(info.eol_esm_year)
