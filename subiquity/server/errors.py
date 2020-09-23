# Copyright 2020 Canonical, Ltd.
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

from subiquity.common.types import ErrorReportState, ErrorReportRef


class ErrorController:

    def __init__(self, app):
        self.context = app.context.child("Error")
        self.error_reporter = app.error_reporter

    async def wait_GET(self, error_ref: ErrorReportRef) -> ErrorReportRef:
        report = self.error_reporter.get(error_ref)
        if report.state == ErrorReportState.INCOMPLETE:
            await report._info_task
        return report.ref()
