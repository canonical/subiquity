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

import enum
from typing import List, Optional

from subiquitycore.models.network import (
    BondConfig,
    NetDevInfo,
    StaticConfig,
    )

from subiquity.common.api.defs import api, Payload, simple_endpoint
from subiquity.common.types import (
    ApplicationState,
    ApplicationStatus,
    ErrorReportRef,
    KeyboardSetting,
    IdentityData,
    InstallState,
    InstallStatus,
    RefreshStatus,
    SnapInfo,
    SnapListResponse,
    SnapSelection,
    SSHData,
    StorageResponse,
    ZdevInfo,
    )


@api
class API:
    """The API offered by the subiquity installer process."""
    locale = simple_endpoint(str)
    keyboard = simple_endpoint(KeyboardSetting)
    proxy = simple_endpoint(str)
    mirror = simple_endpoint(str)
    identity = simple_endpoint(IdentityData)
    ssh = simple_endpoint(SSHData)

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

    class zdev:
        def GET() -> List[ZdevInfo]: ...

        class chzdev:
            def POST(action: str, zdev: ZdevInfo) -> List[ZdevInfo]: ...

    class network:
        def GET() -> List[NetDevInfo]: ...
        def POST() -> None: ...

        class global_addresses:
            def GET() -> List[str]:
                """Return the global IP addresses the system currently has."""

        class subscription:
            """Subscribe to networking updates.

            The socket must serve the NetEventAPI below.
            """
            def PUT(socket_path: str) -> None: ...
            def DELETE(socket_path: str) -> None: ...

        # These methods could definitely be more RESTish, like maybe a
        # GET request to /network/interfaces/$name should return netplan
        # config which could then be POSTed back the same path. But
        # well, that's not implemented yet.
        #
        # (My idea is that the API definition would look something like
        #
        # class network:
        #     class interfaces:
        #        class dev_name:
        #            __subscript__ = True
        #            def GET() -> dict: ...
        #            def POST(config: Payload[dict]) -> None: ...
        #
        # The client would use subscripting to get a client for
        # the nic, so something like
        #
        #   dev_client = client.network[dev_name]
        #   config = await dev_client.GET()
        #   ...
        #   await dev_client.POST(config)
        #
        # The implementation would look like:
        #
        # class NetworkController:
        #
        #     async def interfaces_devname_GET(dev_name: str) -> dict: ...
        #     async def interfaces_devname_POST(dev_name: str, config: dict) \
        #       -> None: ...
        #
        # So methods on nics get an extra dev_name: str parameter)

        class set_static_config:
            def POST(dev_name: str, ip_version: int,
                     static_config: Payload[StaticConfig]) -> None: ...

        class enable_dhcp:
            def POST(dev_name: str, ip_version: int) -> None: ...

        class disable:
            def POST(dev_name: str, ip_version: int) -> None: ...

        class vlan:
            def PUT(dev_name: str, vlan_id: int) -> None: ...

        class add_or_edit_bond:
            def POST(existing_name: Optional[str], new_name: str,
                     bond_config: Payload[BondConfig]) -> None: ...

        class delete:
            def POST(dev_name: str) -> None: ...

        class info:
            def GET(dev_name: str) -> str: ...

    class storage:
        def GET(wait: bool = False) -> StorageResponse: ...
        def POST(config: Payload[list]): ...

        class reset:
            def POST() -> StorageResponse: ...

    class snaplist:
        def GET(wait: bool = False) -> SnapListResponse: ...
        def POST(data: Payload[List[SnapSelection]]): ...

        class snap_info:
            def GET(snap_name: str) -> SnapInfo: ...

    class install:
        class status:
            def GET(cur: Optional[InstallState] = None) -> InstallStatus: ...

    class reboot:
        def POST(): ...


class LinkAction(enum.Enum):
    NEW = enum.auto()
    CHANGE = enum.auto()
    DEL = enum.auto()


@api
class NetEventAPI:
    class update_link:
        def POST(act: LinkAction, info: Payload[NetDevInfo]) -> None: ...

    class route_watch:
        def POST(routes: List[int]) -> None: ...

    class apply_starting:
        def POST() -> None: ...

    class apply_stopping:
        def POST() -> None: ...

    class apply_error:
        def POST(stage: str) -> None: ...
