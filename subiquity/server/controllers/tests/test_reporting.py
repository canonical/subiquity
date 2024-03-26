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

from unittest.mock import Mock, patch

import jsonschema
from curtin.reporter.events import status as CurtinStatus
from jsonschema.validators import validator_for

from subiquity.server.controllers.reporting import ReportingController
from subiquitycore.context import Context
from subiquitycore.context import Status as ContextStatus
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import MockedApplication, make_app


class TestReportingController(SubiTestCase):
    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            ReportingController.autoinstall_schema
        )

        JsonValidator.check_schema(ReportingController.autoinstall_schema)


@patch("subiquity.server.controllers.reporting.report_event")
class TestReportingCurtinCalls(SubiTestCase):
    def setUp(self):
        app: MockedApplication = make_app()
        self.controller: ReportingController = ReportingController(app)
        self.context: Context = app.context

    @patch("subiquity.server.controllers.reporting.report_start_event")
    def test_start_event(self, report_start_event, report_event):
        self.controller.report_start_event(self.context, "description")

        # Calls specific start event method
        report_start_event.assert_called_with(
            self.context.full_name(), "description", level=self.context.level
        )

        # Not the generic one
        report_event.assert_not_called()

    @patch("subiquity.server.controllers.reporting.report_finish_event")
    def test_finish_event(self, report_finish_event, report_event):
        self.controller.report_finish_event(
            self.context, "description", ContextStatus.FAIL
        )

        # Calls specific finish event method
        report_finish_event.assert_called_with(
            self.context.full_name(),
            "description",
            CurtinStatus.FAIL,
            level=self.context.level,
        )

        # Not the generic one
        report_event.assert_not_called()

        # Test default WARN
        status = Mock()
        status.name = "NEW LEVEL"
        self.controller.report_finish_event(self.context, "description", status)

        report_finish_event.assert_called_with(
            self.context.full_name(),
            "description",
            CurtinStatus.WARN,
            level=self.context.level,
        )

    @patch("subiquity.server.controllers.reporting.ReportingEvent")
    def test_info_event(self, mock_class, report_event):
        self.controller.report_info_event(self.context, "description")

        mock_class.assert_called_with(
            "info",
            self.context.full_name(),
            "description",
            level="INFO",
        )

    @patch("subiquity.server.controllers.reporting.ReportingEvent")
    def test_warning_event(self, mock_class, report_event):
        self.controller.report_warning_event(self.context, "description")

        mock_class.assert_called_with(
            "warning",
            self.context.full_name(),
            "description",
            level="WARNING",
        )

    @patch("subiquity.server.controllers.reporting.ReportingEvent")
    def test_error_event(self, mock_class, report_event):
        self.controller.report_error_event(self.context, "description")

        mock_class.assert_called_with(
            "error",
            self.context.full_name(),
            "description",
            level="ERROR",
        )
