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

from typing import List, Optional

from subiquity.common.api.defs import api, simple_endpoint
from subiquity.common.types import (
    ApplicationState,
    ApplicationStatus,
    ErrorReportRef,
    KeyboardSetting,
    InstallState,
    InstallStatus,
    RefreshStatus,
    )


@api
class API:
    """The API offered by the subiquity installer process."""
    locale = simple_endpoint(str)
    keyboard = simple_endpoint(KeyboardSetting)

    class meta:
        class status:
            def GET(cur: Optional[ApplicationState] = None) \
              -> ApplicationStatus:
                """Get the installer state."""

        class mark_configured:
            def POST(endpoint_names: List[str]) -> None:
                """Mark the controllers for endpoint_names as configured."""

        class confirm:
            def POST(tty: str) -> None:
                """Confirm that the installation should proceed."""

        class restart:
            def POST() -> None:
                """Restart the server process."""
    class errors:
        class wait:
            def GET(error_ref: ErrorReportRef) -> ErrorReportRef:
                """Block until the error report is fully populated."""

    class dry_run:
        """This endpoint only works in dry-run mode."""

        class crash:
            def GET() -> None:
                """Requests to this method will fail with a HTTP 500."""

    class refresh:
        def GET(wait: bool = False) -> RefreshStatus:
            """Get information about the snap refresh status.

            If wait is true, block until the status is known."""

        def POST() -> int:
            """Start the update and return the change id."""

        class progress:
            def GET(change_id: int) -> dict: ...

    class install:
        class status:
            def GET(cur: Optional[InstallState] = None) -> InstallStatus: ...
