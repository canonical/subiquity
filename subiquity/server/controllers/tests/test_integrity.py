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

from subiquity.common.types import CasperMd5Results
from subiquity.models.integrity import IntegrityModel
from subiquity.server.controllers.integrity import (
    IntegrityController,
    mock_fail,
    mock_pass,
    mock_skip,
)
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app


class TestMd5Check(SubiTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = "UEFI"
        self.ic = IntegrityController(app=self.app)
        self.ic.model = IntegrityModel()

    def test_pass(self):
        self.ic.model.md5check_results = mock_pass
        self.assertEqual(CasperMd5Results.PASS, self.ic.result)

    def test_skip(self):
        self.ic.model.md5check_results = mock_skip
        self.assertEqual(CasperMd5Results.SKIP, self.ic.result)

    def test_unknown(self):
        self.assertEqual(CasperMd5Results.UNKNOWN, self.ic.result)

    def test_fail(self):
        self.ic.model.md5check_results = mock_fail
        self.assertEqual(CasperMd5Results.FAIL, self.ic.result)
