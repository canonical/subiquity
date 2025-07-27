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

from subiquity.common.api.defs import (
    Payload,
    allowed_before_start,
    api,
    simple_endpoint,
)
from subiquity.common.types import (
    AdAdminNameValidation,
    AdConnectionInfo,
    AdDomainNameValidation,
    AdJoinResult,
    AdPasswordValidation,
    AnyStep,
    ApplicationState,
    ApplicationStatus,
    CasperMd5Results,
    Change,
    CodecsData,
    DriversPayload,
    DriversResponse,
    ErrorReportRef,
    IdentityData,
    KeyboardSetting,
    KeyboardSetup,
    LiveSessionSSHInfo,
    MirrorCheckResponse,
    MirrorGet,
    MirrorPost,
    MirrorPostResponse,
    MirrorSelectionFallback,
    NetworkStatus,
    OEMResponse,
    PackageInstallState,
    RefreshStatus,
    ShutdownMode,
    SnapInfo,
    SnapListResponse,
    SnapSelection,
    SourceSelectionAndSetting,
    SSHData,
    SSHFetchIdResponse,
    TimeZoneInfo,
    UbuntuProCheckTokenAnswer,
    UbuntuProGeneralInfo,
    UbuntuProInfo,
    UbuntuProResponse,
    UPCSInitiateResponse,
    UPCSWaitResponse,
    UsernameValidation,
    ZdevInfo,
)
from subiquity.common.types.storage import (
    AddPartitionV2,
    CalculateEntropyRequest,
    Disk,
    EntropyResponse,
    GuidedChoiceV2,
    GuidedStorageResponseV2,
    ModifyPartitionV2,
    ReformatDisk,
    StorageResponse,
    StorageResponseV2,
)
from subiquitycore.models.network import (
    BondConfig,
    NetDevInfo,
    StaticConfig,
    WLANConfig,
)


@api
class API:
    """The API offered by the subiquity installer process."""

    locale = simple_endpoint(str)
    proxy = simple_endpoint(str)
    updates = simple_endpoint(str)

    class meta:
        class status:
            @allowed_before_start
            def GET(cur: Optional[ApplicationState] = None) -> ApplicationStatus:
                """Get the installer state."""

        class mark_configured:
            def POST(endpoint_names: List[str]) -> None:
                """Mark the controllers for endpoint_names as configured."""

        class client_variant:
            def POST(variant: str) -> None:
                """Choose the install variant - desktop/server"""

            def GET() -> str:
                """Get the install variant - desktop/server"""

        class confirm:
            def POST(tty: str) -> None:
                """Confirm that the installation should proceed."""

        class restart:
            @allowed_before_start
            def POST() -> None:
                """Restart the server process."""

        class ssh_info:
            @allowed_before_start
            def GET() -> Optional[LiveSessionSSHInfo]: ...

        class free_only:
            def GET() -> bool: ...

            def POST(enable: bool) -> None:
                """Enable or disable free-only mode.  Currently only controlls
                the list of components.  free-only choice must be made prior to
                confirmation of filesystem changes"""

        class interactive_sections:
            def GET() -> Optional[List[str]]: ...

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
            def GET(change_id: str) -> Change: ...

    class keyboard:
        def GET() -> KeyboardSetup: ...

        def POST(data: Payload[KeyboardSetting]): ...

        class needs_toggle:
            def GET(layout_code: str, variant_code: str) -> bool: ...

        class steps:
            def GET(index: Optional[str]) -> AnyStep: ...

        class input_source:
            def POST(
                data: Payload[KeyboardSetting], user: Optional[str] = None
            ) -> None: ...

    class source:
        def GET() -> SourceSelectionAndSetting: ...

        def POST(source_id: str, search_drivers: bool = False) -> None: ...

    class zdev:
        def GET() -> List[ZdevInfo]: ...

        class chzdev:
            def POST(action: str, zdev: ZdevInfo) -> List[ZdevInfo]: ...

    class network:
        def GET() -> NetworkStatus: ...

        def POST() -> None: ...

        class has_network:
            def GET() -> bool: ...

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
            def POST(
                dev_name: str, ip_version: int, static_config: Payload[StaticConfig]
            ) -> None: ...

        class enable_dhcp:
            def POST(dev_name: str, ip_version: int) -> None: ...

        class disable:
            def POST(dev_name: str, ip_version: int) -> None: ...

        class vlan:
            def PUT(dev_name: str, vlan_id: int) -> None: ...

        class add_or_edit_bond:
            def POST(
                existing_name: Optional[str],
                new_name: str,
                bond_config: Payload[BondConfig],
            ) -> None: ...

        class start_scan:
            def POST(dev_name: str) -> None: ...

        class set_wlan:
            def POST(dev_name: str, wlan: WLANConfig) -> None: ...

        class delete:
            def POST(dev_name: str) -> None: ...

        class info:
            def GET(dev_name: str) -> str: ...

    class storage:
        def GET(
            wait: bool = False, use_cached_result: bool = False
        ) -> StorageResponse: ...

        def POST(config: Payload[list]): ...

        class dry_run_wait_probe:
            """This endpoint only works in dry-run mode."""

            def POST() -> None: ...

        class has_rst:
            def GET() -> bool:
                pass

        class has_bitlocker:
            def GET() -> List[Disk]: ...

        class generate_recovery_key:
            def GET() -> str: ...

        class supports_nvme_tcp_booting:
            def GET(wait: bool = False) -> Optional[bool]:
                """Tells whether the firmware supports booting with NVMe/TCP.
                If Subiquity hasn't yet determined if NVMe/TCP booting is
                supported, the response will vary based on the value of wait:
                * if wait is True, then Subiquity will send the response once
                it has figured out.
                * if wait is False, then Subiquity will return None.
                """

        class v2:
            def GET(
                wait: bool = False,
                include_raid: bool = False,
            ) -> StorageResponseV2: ...

            def POST() -> StorageResponseV2: ...

            class orig_config:
                def GET() -> StorageResponseV2: ...

            class guided:
                def GET(wait: bool = False) -> GuidedStorageResponseV2: ...

                def POST(data: Payload[GuidedChoiceV2]) -> GuidedStorageResponseV2: ...

            class reset:
                def POST() -> StorageResponseV2: ...

            class ensure_transaction:
                """This call will ensure that a transaction is initiated.
                During a transaction, storage probing runs are not permitted to
                reset the partitioning configuration.
                A transaction will also be initiated by any v2_storage POST
                request that modifies the partitioning configuration (e.g.,
                add_partition, edit_partition, ...) but ensure_transaction can
                be called early if desired."""

                def POST() -> None: ...

            class reformat_disk:
                def POST(data: Payload[ReformatDisk]) -> StorageResponseV2: ...

            class add_boot_partition:
                """Mark a given disk as bootable, which may cause a partition
                to be added to the disk.  It is an error to call this for a
                disk for which can_be_boot_device is False."""

                def POST(disk_id: str) -> StorageResponseV2: ...

            class add_partition:
                """required field format and mount, optional field size
                default behavior expands partition to fill disk if size not
                supplied or -1.
                Other partition fields are ignored.
                adding a partion when there is not yet a boot partition can
                result in the boot partition being added automatically - see
                add_boot_partition for more control over this.
                format=None means an unformatted partition
                """

                def POST(data: Payload[AddPartitionV2]) -> StorageResponseV2: ...

            class delete_partition:
                """required field number
                It is an error to modify other Partition fields.
                """

                def POST(data: Payload[ModifyPartitionV2]) -> StorageResponseV2: ...

            class edit_partition:
                """required field number
                optional fields wipe, mount, format, size
                It is an error to do wipe=null and change the format.
                It is an error to modify other Partition fields.
                """

                def POST(data: Payload[ModifyPartitionV2]) -> StorageResponseV2: ...

            class volume_group:
                def DELETE(id: str) -> StorageResponseV2:
                    """Delete the VG specified by its ID. Any associated LV
                    will be deleted as well."""

            class logical_volume:
                def DELETE(id: str) -> StorageResponseV2:
                    """Delete the LV specified by its ID."""

            class raid:
                def DELETE(id: str) -> StorageResponseV2:
                    """Delete the Raid specified by its ID. Any associated
                    partition will be deleted as well."""

            class calculate_entropy:
                def POST(data: Payload[CalculateEntropyRequest]) -> EntropyResponse:
                    """Calculate the entropy associated with the supplied
                    passphrase or pin.  Clients must use this endpoint to
                    confirm that the pin or passphrase is suitable prior to
                    configuring CORE_BOOT_ENCRYPTED, and may use it in other
                    scenarios."""

            class core_boot_recovery_key:
                def GET() -> str: ...

    class codecs:
        def GET() -> CodecsData: ...

        def POST(data: Payload[CodecsData]) -> None: ...

    class drivers:
        def GET(wait: bool = False) -> DriversResponse: ...

        def POST(data: Payload[DriversPayload]) -> None: ...

    class oem:
        def GET(wait: bool = False) -> OEMResponse: ...

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
        def GET() -> MirrorGet: ...

        def POST(data: Payload[Optional[MirrorPost]]) -> MirrorPostResponse: ...

        class disable_components:
            def GET() -> List[str]: ...

            def POST(data: Payload[List[str]]): ...

        class check_mirror:
            class start:
                def POST(cancel_ongoing: bool = False) -> None: ...

            class progress:
                def GET() -> Optional[MirrorCheckResponse]: ...

            class abort:
                def POST() -> None: ...

        fallback = simple_endpoint(MirrorSelectionFallback)

    class ubuntu_pro:
        def GET() -> UbuntuProResponse: ...

        def POST(data: Payload[UbuntuProInfo]) -> None: ...

        class skip:
            def POST() -> None: ...

        class check_token:
            def GET(token: Payload[str]) -> UbuntuProCheckTokenAnswer: ...

        class contract_selection:
            class initiate:
                def POST() -> UPCSInitiateResponse: ...

            class wait:
                def GET() -> UPCSWaitResponse: ...

            class cancel:
                def POST() -> None: ...

        class info:
            def GET() -> UbuntuProGeneralInfo: ...

    class identity:
        def GET() -> IdentityData: ...

        def POST(data: Payload[IdentityData]): ...

        class validate_username:
            def GET(username: str) -> UsernameValidation: ...

    class ssh:
        def GET() -> SSHData: ...

        def POST(data: Payload[SSHData]) -> None: ...

        class fetch_id:
            def GET(user_id: str) -> SSHFetchIdResponse: ...

    class integrity:
        @allowed_before_start
        def GET(wait=False) -> CasperMd5Results: ...

    class active_directory:
        def GET() -> Optional[AdConnectionInfo]: ...

        # POST expects input validated by the check methods below:
        def POST(data: Payload[AdConnectionInfo]) -> None: ...

        class has_support:
            """Whether the live system supports Active Directory or not.
            Network status is not considered.
            Clients should call this before showing the AD page."""

            def GET() -> bool: ...

        class check_domain_name:
            """Applies basic validation to the candidate domain name,
            without calling the domain network."""

            def POST(domain_name: Payload[str]) -> List[AdDomainNameValidation]: ...

        class ping_domain_controller:
            """Attempts to contact the controller of the provided domain."""

            def POST(domain_name: Payload[str]) -> AdDomainNameValidation: ...

        class check_admin_name:
            def POST(admin_name: Payload[str]) -> AdAdminNameValidation: ...

        class check_password:
            def POST(password: Payload[str]) -> AdPasswordValidation: ...

        class join_result:
            def GET(wait: bool = True) -> AdJoinResult: ...


class LinkAction(enum.Enum):
    NEW = enum.auto()
    CHANGE = enum.auto()
    DEL = enum.auto()


@api
class NetEventAPI:
    class wlan_support_install_finished:
        def POST(state: PackageInstallState) -> None: ...

    class update_link:
        def POST(act: LinkAction, info: Payload[NetDevInfo]) -> None: ...

    class route_watch:
        def POST(has_default_route: bool) -> None: ...

    class apply_starting:
        def POST() -> None: ...

    class apply_stopping:
        def POST() -> None: ...

    class apply_error:
        def POST(stage: str) -> None: ...
