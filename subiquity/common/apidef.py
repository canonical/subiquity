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
    WLANConfig,
    )

from subiquity.common.api.defs import api, Payload, simple_endpoint
from subiquity.common.types import (
    AnyStep,
    ApplicationState,
    ApplicationStatus,
    Disk,
    ErrorReportRef,
    GuidedChoice,
    GuidedStorageResponse,
    KeyboardSetting,
    KeyboardSetup,
    IdentityData,
    NetworkStatus,
    ModifyPartitionV2,
    RefreshStatus,
    ShutdownMode,
    SnapInfo,
    SnapListResponse,
    SnapSelection,
    SourceSelectionAndSetting,
    SSHData,
    LiveSessionSSHInfo,
    StorageResponse,
    StorageResponseV2,
    TimeZoneInfo,
    UbuntuAdvantageInfo,
    UbuntuAdvantageCheckTokenAnswer,
    WLANSupportInstallState,
    ZdevInfo,
    WSLConfigurationBase,
    WSLConfigurationAdvanced,
    )


@api
class API:
    """The API offered by the subiquity installer process."""
    identity = simple_endpoint(IdentityData)
    locale = simple_endpoint(str)
    proxy = simple_endpoint(str)
    ssh = simple_endpoint(SSHData)
    updates = simple_endpoint(str)
    wslconfbase = simple_endpoint(WSLConfigurationBase)
    wslconfadvanced = simple_endpoint(WSLConfigurationAdvanced)

    class meta:
        class status:
            def GET(cur: Optional[ApplicationState] = None) \
              -> ApplicationStatus:
                """Get the installer state."""

        class mark_configured:
            def POST(endpoint_names: List[str]) -> None:
                """Mark the controllers for endpoint_names as configured."""

        class client_variant:
            def POST(variant: str) -> None:
                """Choose the install variant -
                desktop/server/wsl_setup/wsl_reconfigure"""
            def GET() -> str:
                """Get the install variant -
                desktop/server/wsl_setup/wsl_reconfigure"""

        class confirm:
            def POST(tty: str) -> None:
                """Confirm that the installation should proceed."""

        class restart:
            def POST() -> None:
                """Restart the server process."""

        class ssh_info:
            def GET() -> Optional[LiveSessionSSHInfo]: ...

        class free_only:
            def GET() -> bool: ...

            def POST(enable: bool) -> None:
                """Enable or disable free-only mode.  Currently only controlls
                the list of components.  free-only choice must be made prior to
                confirmation of filesystem changes"""

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

        def POST() -> str:
            """Start the update and return the change id."""

        class progress:
            def GET(change_id: str) -> dict: ...

    class keyboard:
        def GET() -> KeyboardSetup: ...
        def POST(data: Payload[KeyboardSetting]): ...

        class needs_toggle:
            def GET(layout_code: str, variant_code: str) -> bool: ...

        class steps:
            def GET(index: Optional[str]) -> AnyStep: ...

    class source:
        def GET() -> SourceSelectionAndSetting: ...
        def POST(source_id: str) -> None: ...

    class zdev:
        def GET() -> List[ZdevInfo]: ...

        class chzdev:
            def POST(action: str, zdev: ZdevInfo) -> List[ZdevInfo]: ...

    class network:
        def GET() -> NetworkStatus: ...
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

        class start_scan:
            def POST(dev_name: str) -> None: ...

        class set_wlan:
            def POST(dev_name: str, wlan: WLANConfig) -> None: ...

        class delete:
            def POST(dev_name: str) -> None: ...

        class info:
            def GET(dev_name: str) -> str: ...

    class storage:
        class guided:
            def GET(wait: bool = False) -> GuidedStorageResponse:
                pass

            def POST(data: Payload[GuidedChoice]) \
                    -> StorageResponse:
                pass

        def GET(wait: bool = False) -> StorageResponse: ...
        def POST(config: Payload[list]): ...

        class reset:
            def POST() -> StorageResponse: ...

        class has_rst:
            def GET() -> bool:
                pass

        class has_bitlocker:
            def GET() -> List[Disk]: ...

        class v2:
            def GET() -> StorageResponseV2: ...
            def POST() -> StorageResponseV2: ...

            class guided:
                def POST(data: Payload[GuidedChoice]) \
                    -> StorageResponseV2: ...

            class reset:
                def POST() -> StorageResponseV2: ...

            class reformat_disk:
                def POST(disk_id: str) -> StorageResponseV2: ...

            class add_boot_partition:
                def POST(disk_id: str) -> StorageResponseV2: ...

            class add_partition:
                """required field format and mount, optional field size
                   default behavior expands partition to fill disk if size not
                   supplied or -1.
                   Other partition fields are ignored.
                   adding a partion when there is not yet a boot partition can
                   result in the boot partition being added automatically - see
                   add_boot_partition for more control over this.
                """
                def POST(data: Payload[ModifyPartitionV2]) \
                    -> StorageResponseV2: ...

            class delete_partition:
                """required field number
                   It is an error to modify other Partition fields.
                """
                def POST(data: Payload[ModifyPartitionV2]) \
                    -> StorageResponseV2: ...

            class edit_partition:
                """required field number
                   optional fields wipe, mount, format
                   It is an error to do wipe=null and change the format.
                   It is an error to modify other Partition fields.
                """
                def POST(data: Payload[ModifyPartitionV2]) \
                    -> StorageResponseV2: ...

    class drivers:
        def GET(wait: bool = False) -> bool: ...
        def POST(install: bool): ...

    class snaplist:
        def GET(wait: bool = False) -> SnapListResponse: ...
        def POST(data: Payload[List[SnapSelection]]): ...

        class snap_info:
            def GET(snap_name: str) -> SnapInfo: ...

    class timezone:
        def GET() -> TimeZoneInfo: ...
        def POST(tz: str): ...

    class shutdown:
        def POST(mode: ShutdownMode, immediate: bool = False): ...

    class mirror:
        def GET() -> str: ...
        def POST(data: Payload[str]): ...

        class disable_components:
            def GET() -> List[str]: ...
            def POST(data: Payload[List[str]]): ...

    class ubuntu_advantage:
        def GET() -> UbuntuAdvantageInfo: ...
        def POST(data: Payload[UbuntuAdvantageInfo]) -> None: ...

        class skip:
            def POST() -> None: ...

        class check_token:
            def GET(token: Payload[str]) \
                    -> UbuntuAdvantageCheckTokenAnswer: ...


class LinkAction(enum.Enum):
    NEW = enum.auto()
    CHANGE = enum.auto()
    DEL = enum.auto()


@api
class NetEventAPI:
    class wlan_support_install_finished:
        def POST(state: WLANSupportInstallState) -> None: ...

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
