# Copyright 2025 Canonical, Ltd.
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

from unittest.mock import AsyncMock, Mock, patch

from subiquity.client.controllers.source import SourceController
from subiquity.common.types import SourceSelectionAndSetting
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized
from subiquitycore.tuicontroller import Skip


class TestSourceController(SubiTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.client = AsyncMock()
        self.app.show_error_report = Mock()
        self.app.show_nonreportable_error = Mock()

        self.controller = SourceController(self.app)

    @parameterized.expand(
        (
            ("core", 1, True),  # core is the only driverless variant
            ("core", 2, False),  # don't skip if core has multiple sources
            ("server", 1, False),  # Any other variant shouldn't skip
        )
    )
    async def test_make_ui__skip_simple_sources(self, variant, sources, skip):
        """Test source screen is skipped for single-source, driverless media."""

        self.app.variant = variant
        resp = SourceSelectionAndSetting(
            sources=[Mock() for i in range(sources)],
            current_id=0,
            search_drivers=None,
        )

        with (
            patch("subiquity.client.controllers.source.SourceView"),
            patch.object(self.controller.endpoint, "GET", return_value=resp),
        ):
            if not skip:
                await self.controller.make_ui()
            else:
                with self.assertRaises(Skip):
                    await self.controller.make_ui()
