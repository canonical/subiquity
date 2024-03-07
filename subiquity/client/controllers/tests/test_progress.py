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

import unittest
from unittest.mock import AsyncMock, Mock

from subiquity.client.controllers.progress import ProgressController
from subiquity.common.types import ApplicationState, ApplicationStatus
from subiquitycore.tests.mocks import make_app


class TestProgressController(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        app = make_app()
        app.client = AsyncMock()
        app.show_error_report = Mock()
        app.show_nonreportable_error = Mock()

        self.controller = ProgressController(app)

    async def test_handle_error_state(self):
        # Reportable error case

        status: ApplicationStatus = ApplicationStatus(
            state=ApplicationState.ERROR,
            confirming_tty="",
            error=Mock(),
            nonreportable_error=None,
            cloud_init_ok=Mock(),
            interactive=Mock(),
            echo_syslog_id=Mock(),
            log_syslog_id=Mock(),
            event_syslog_id=Mock(),
        )

        self.controller._handle_error_state(status)
        self.controller.app.show_error_report.assert_called_once()
        self.controller.app.show_nonreportable_error.assert_not_called()

        # Reset mocks between cases
        self.controller.app.show_error_report.reset_mock()
        self.controller.app.show_nonreportable_error.reset_mock()

        # Non Reportable error case

        status: ApplicationStatus = ApplicationStatus(
            state=ApplicationState.ERROR,
            confirming_tty="",
            error=None,
            nonreportable_error=Mock(),
            cloud_init_ok=Mock(),
            interactive=Mock(),
            echo_syslog_id=Mock(),
            log_syslog_id=Mock(),
            event_syslog_id=Mock(),
        )

        self.controller._handle_error_state(status)
        self.controller.app.show_error_report.assert_not_called()
        self.controller.app.show_nonreportable_error.assert_called_once()

        # Reset mocks between cases
        self.controller.app.show_error_report.reset_mock()
        self.controller.app.show_nonreportable_error.reset_mock()

        # Bug case

        status: ApplicationStatus = ApplicationStatus(
            state=ApplicationState.ERROR,
            confirming_tty="",
            error=None,
            nonreportable_error=None,
            cloud_init_ok=Mock(),
            interactive=Mock(),
            echo_syslog_id=Mock(),
            log_syslog_id=Mock(),
            event_syslog_id=Mock(),
        )

        with self.assertRaises(Exception):
            self.controller._handle_error_state(status)
        self.controller.app.show_error_report.assert_not_called()
        self.controller.app.show_nonreportable_error.assert_not_called()
