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

import asyncio
import copy
import logging
import os
import sys
import time
from typing import Any, List, Optional

import jsonschema
import yaml
from aiohttp import web
from jsonschema.exceptions import ValidationError
from systemd import journal

from subiquity.cloudinit import (
    CloudInitSchemaTopLevelKeyError,
    cloud_init_status_wait,
    get_host_combined_cloud_config,
    legacy_cloud_init_extract,
    rand_user_password,
    validate_cloud_init_top_level_keys,
)
from subiquity.common.api.recoverable_error import RecoverableError
from subiquity.common.api.server import bind, controller_for_request
from subiquity.common.apidef import API
from subiquity.common.errorreport import ErrorReport, ErrorReporter, ErrorReportKind
from subiquity.common.serialize import to_json
from subiquity.common.types import (
    ApplicationState,
    ApplicationStatus,
    ErrorReportRef,
    KeyFingerprint,
    LiveSessionSSHInfo,
    NonReportableError,
    PasswordKind,
)
from subiquity.models.subiquity import ModelNames, SubiquityModel
from subiquity.server.autoinstall import AutoinstallError, AutoinstallValidationError
from subiquity.server.controller import SubiquityController
from subiquity.server.dryrun import DRConfig
from subiquity.server.errors import ErrorController
from subiquity.server.event_listener import EventListener
from subiquity.server.geoip import DryRunGeoIPStrategy, GeoIP, HTTPGeoIPStrategy
from subiquity.server.nonreportable import NonReportableException
from subiquity.server.pkghelper import get_package_installer
from subiquity.server.runner import get_command_runner
from subiquity.server.snapd.api import make_api_client
from subiquity.server.snapd.info import SnapdInfo
from subiquity.server.types import InstallerChannels
from subiquitycore.async_helpers import run_bg_task, run_in_thread
from subiquitycore.context import Context, with_context
from subiquitycore.core import Application
from subiquitycore.file_util import copy_file_if_exists, write_file
from subiquitycore.prober import Prober
from subiquitycore.snapd import AsyncSnapd, SnapdConnection, get_fake_connection
from subiquitycore.ssh import host_key_fingerprints, user_key_fingerprints
from subiquitycore.utils import run_command

NOPROBERARG = "NOPROBER"

iso_autoinstall_path = "cdrom/autoinstall.yaml"
root_autoinstall_path = "autoinstall.yaml"
cloud_autoinstall_path = "run/subiquity/cloud.autoinstall.yaml"

log = logging.getLogger("subiquity.server.server")


class MetaController:
    def __init__(self, app):
        self.app = app
        self.context = app.context.child("Meta")
        self.free_only = False

    async def status_GET(
        self, cur: Optional[ApplicationState] = None
    ) -> ApplicationStatus:
        if cur == self.app.state:
            await self.app.state_event.wait()
        return ApplicationStatus(
            state=self.app.state,
            confirming_tty=self.app.confirming_tty,
            error=self.app.fatal_error,
            nonreportable_error=self.app.nonreportable_error,
            cloud_init_ok=self.app.cloud_init_ok,
            interactive=self.app.interactive,
            echo_syslog_id=self.app.echo_syslog_id,
            event_syslog_id=self.app.event_syslog_id,
            log_syslog_id=self.app.log_syslog_id,
        )

    async def confirm_POST(self, tty: str) -> None:
        self.app.confirming_tty = tty
        await self.app.base_model.confirm()

    async def restart_POST(self) -> None:
        self.app.restart()

    async def mark_configured_POST(self, endpoint_names: List[str]) -> None:
        endpoints = {getattr(API, en, None) for en in endpoint_names}
        for controller in self.app.controllers.instances:
            if controller.endpoint in endpoints:
                await controller.configured()

    # TODO: Make post to /meta/client_variant a RecoverableError (it doesn't
    # have to be fatal and it's currently only pseudo-fatal).
    async def client_variant_POST(self, variant: str) -> None:
        if variant not in self.app.supported_variants:
            raise ValueError(f"unrecognized client variant {variant}")
        self.app.set_source_variant(variant)

    async def client_variant_GET(self) -> str:
        return self.app.variant

    async def ssh_info_GET(self) -> Optional[LiveSessionSSHInfo]:
        ips: List[str] = []
        if self.app.base_model.network:
            for dev in self.app.base_model.network.get_all_netdevs():
                if dev.info is None:
                    continue
                ips.extend(map(str, dev.actual_global_ip_addresses))
        if not ips:
            return None
        username = self.app.installer_user_name
        if username is None:
            return None
        user_fingerprints = [
            KeyFingerprint(keytype, fingerprint)
            for keytype, fingerprint in user_key_fingerprints(username)
        ]
        if self.app.installer_user_passwd_kind == PasswordKind.NONE:
            if not user_key_fingerprints:
                return None
        host_fingerprints = [
            KeyFingerprint(keytype, fingerprint)
            for keytype, fingerprint in host_key_fingerprints()
        ]
        return LiveSessionSSHInfo(
            username=username,
            password_kind=self.app.installer_user_passwd_kind,
            password=self.app.installer_user_passwd,
            authorized_key_fingerprints=user_fingerprints,
            ips=ips,
            host_key_fingerprints=host_fingerprints,
        )

    async def free_only_GET(self) -> bool:
        return self.free_only

    async def free_only_POST(self, enable: bool) -> None:
        self.free_only = enable
        to_disable = {"restricted", "multiverse"}
        # enabling free only mode means disabling components
        self.app.base_model.mirror.disable_components(to_disable, enable)

    async def interactive_sections_GET(self) -> Optional[List[str]]:
        if self.app.autoinstall_config is None:
            return None

        i_sections = self.app.autoinstall_config.get("interactive-sections", None)
        if i_sections == ["*"]:
            # expand the asterisk to the actual controller key names
            return [
                controller.autoinstall_key
                for controller in self.app.controllers.instances
                if controller.interactive()
                if controller.autoinstall_key is not None
            ]

        return i_sections


def get_installer_password_from_cloudinit_log():
    try:
        fp = open("/var/log/cloud-init-output.log")
    except FileNotFoundError:
        return None

    with fp:
        for line in fp:
            if line.startswith("installer:"):
                return line[len("installer:") :].strip()

    return None


INSTALL_MODEL_NAMES = ModelNames(
    {
        "debconf_selections",
        "filesystem",
        "kernel",
        "kernel_crash_dumps",
        "keyboard",
        "source",
    },
    desktop={"network"},
    server={"mirror", "network", "proxy"},
)

POSTINSTALL_MODEL_NAMES = ModelNames(
    {
        "drivers",
        "identity",
        "locale",
        "packages",
        "snaplist",
        "ssh",
        "ubuntu_pro",
        "userdata",
    },
    desktop={"timezone", "codecs", "active_directory", "network"},
    server={"network"},
)


class SubiquityServer(Application):
    snapd_socket_path = "/run/snapd.socket"

    base_schema = {
        "type": "object",
        "properties": {
            "version": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1,
            },
            "interactive-sections": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
        },
        "required": ["version"],
        "additionalProperties": True,
    }

    project = "subiquity"
    from subiquity.server import controllers as controllers_mod

    controllers = [
        "Early",
        "Reporting",
        "Error",
        "Userdata",
        "Package",
        "Debconf",
        "Locale",
        "Refresh",
        "Kernel",
        "KernelCrashDumps",
        "Integrity",
        "Keyboard",
        "Zdev",
        "Source",
        "Network",
        "UbuntuPro",
        "Proxy",
        "Mirror",
        "Filesystem",
        "Identity",
        "SSH",
        "SnapList",
        "Ad",
        "Codecs",
        "Drivers",
        "OEM",
        "TimeZone",
        "Install",
        "Updates",
        "Late",
        "Shutdown",
    ]

    supported_variants = ["server", "desktop", "core"]

    def make_model(self):
        root = "/"
        if self.opts.dry_run:
            root = os.path.abspath(self.opts.output_base)
        # TODO: Set the model source variant before returning it?
        #       This _will_ eventually get set by the source controller,
        #       but before then it's in a state that only requires the
        #       "default" models i.e., the base set all variants require.
        return SubiquityModel(
            root,
            self.hub,
            INSTALL_MODEL_NAMES,
            POSTINSTALL_MODEL_NAMES,
            opt_supports_nvme_tcp_booting=self.opts.supports_nvme_tcp_booting,
        )

    def __init__(self, opts, block_log_dir):
        super().__init__(opts)
        self.dr_cfg: Optional[DRConfig] = None
        self._set_source_variant(self.supported_variants[0])
        self.block_log_dir = block_log_dir
        self.cloud_init_ok = None
        self.state_event = asyncio.Event()
        self.update_state(ApplicationState.STARTING_UP)
        self.interactive = None
        self.confirming_tty = ""
        self.fatal_error: Optional[ErrorReport] = None
        self.nonreportable_error: Optional[NonReportableError] = None
        self.running_error_commands = False
        self.installer_user_name = None
        self.installer_user_passwd_kind = PasswordKind.NONE
        self.installer_user_passwd = None

        self.echo_syslog_id = "subiquity_echo.{}".format(os.getpid())
        self.event_syslog_id = "subiquity_event.{}".format(os.getpid())
        self.log_syslog_id = "subiquity_log.{}".format(os.getpid())
        self.command_runner = get_command_runner(self)
        self.package_installer = get_package_installer(self)

        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root
        )
        if opts.machine_config == NOPROBERARG:
            self.prober = None
        else:
            self.prober = Prober(opts.machine_config, self.debug_flags)
        self.kernel_cmdline = opts.kernel_cmdline
        if opts.snaps_from_examples:
            connection = get_fake_connection(self.scale_factor, opts.output_base)
            self.snapd = AsyncSnapd(connection)
            self.snapdapi = make_api_client(self.snapd)
            self.snapdinfo = SnapdInfo(self.snapdapi)
        elif os.path.exists(self.snapd_socket_path):
            connection = SnapdConnection(self.root, self.snapd_socket_path)
            self.snapd = AsyncSnapd(connection)
            log_snapd = "subiquity-log-snapd" in self.opts.kernel_cmdline
            self.snapdapi = make_api_client(self.snapd, log_responses=log_snapd)
            self.snapdinfo = SnapdInfo(self.snapdapi)
        else:
            log.info("no snapd socket found. Snap support is disabled")
            self.snapd = None
        self.note_data_for_apport("SnapUpdated", str(self.updated))
        self.event_listeners: list[EventListener] = []
        self.autoinstall_config = None
        self.hub.subscribe(InstallerChannels.NETWORK_UP, self._network_change)
        self.hub.subscribe(InstallerChannels.NETWORK_PROXY_SET, self._proxy_set)
        if self.opts.dry_run:
            geoip_strategy = DryRunGeoIPStrategy()
        else:
            geoip_strategy = HTTPGeoIPStrategy()

        self.geoip = GeoIP(self, strategy=geoip_strategy)

    def _set_source_variant(self, variant):
        self.variant = variant

    def set_source_variant(self, variant):
        """Set the source variant for the install.

        This is the public interface for setting the variant for the install.
        This ensures that both the server and the model's understanding of the
        variant is updated in one place.

        Any extra logic for updating the variant in the server should go into
        the private method _set_source_variant. This is separated out because
        the sever needs to seed the initial variant state during __init__
        but the base_model isn't attached to the server object until the .Run()
        method is called.
        """
        self._set_source_variant(variant)

        self.base_model.set_source_variant(variant)

    def load_serialized_state(self):
        for controller in self.controllers.instances:
            controller.load_state()

    def add_event_listener(self, listener: EventListener):
        self.event_listeners.append(listener)

    def _maybe_push_to_journal(
        self,
        event_type: str,
        context: Context,
        description: Optional[str],
    ):
        # No reporting for request handlers
        if context.get("request", default=None) is not None:
            return

        install_context: bool = context.get("is-install-context", default=False)
        msg: str = ""
        parent_id: str = ""
        indent: int = context.full_name().count("/") - 2

        # We do filtering on which types of events get reported.
        # For interactive installs, we only want to report the event
        # if it's coming from a non-interactive context. The user is aware
        # of the changes being made in interactive sections so lets skip
        # reporting those events.
        #
        # The exceptions to this are:
        #     - special sections of the install, which set "is-install-context"
        #       where we want to report the event anyways
        #
        #     - special event types:
        #       - warn
        #       - error
        #
        # For non-interactive installs (i.e., full autoinstall) we report
        # everything.

        force_reporting: bool = install_context or event_type in ["warning", "error"]

        # self.interactive=None could be an interactive install, we just
        # haven't found out yet
        if self.interactive in [True, None] and not force_reporting:
            # If the event came from a controller and it's interactive,
            # or there's no associated controller so we can't be sure,
            # skip reporting.
            controller = context.get("controller", default=None)
            if controller is None or controller.interactive():
                return

        # Create the message out of the name of the reporter and optionally
        # the description
        name: str = context.full_name()
        if description is not None:
            msg = f"{name}: {description}"
        else:
            msg = name

        # Special case: events from special install contexts which are also
        # interactive get special formatting
        if self.interactive and install_context:
            indent -= 1
            msg = context.description

        indent_prefix: str = " " * indent
        formatted_message: str = f"{indent_prefix}{msg}"

        if context.parent is not None:
            parent_id = str(context.parent.id)
        else:
            parent_id = ""

        journal.send(
            formatted_message,
            PRIORITY=context.level,
            SYSLOG_IDENTIFIER=self.event_syslog_id,
            SUBIQUITY_CONTEXT_NAME=context.full_name(),
            SUBIQUITY_EVENT_TYPE=event_type,
            SUBIQUITY_CONTEXT_ID=str(context.id),
            SUBIQUITY_CONTEXT_PARENT_ID=parent_id,
        )

    def report_start_event(self, context, description):
        for listener in self.event_listeners:
            listener.report_start_event(context, description)
        self._maybe_push_to_journal("start", context, description)

    def report_finish_event(self, context, description, status):
        for listener in self.event_listeners:
            listener.report_finish_event(context, description, status)
        self._maybe_push_to_journal("finish", context, description)

    def report_info_event(self, context: Context, message: str) -> None:
        for listener in self.event_listeners:
            listener.report_info_event(context, message)
        self._maybe_push_to_journal("info", context, message)

    def report_warning_event(self, context: Context, message: str) -> None:
        for listener in self.event_listeners:
            listener.report_warning_event(context, message)
        self._maybe_push_to_journal("warning", context, message)

    def report_error_event(self, context: Context, message: str) -> None:
        for listener in self.event_listeners:
            listener.report_error_event(context, message)
        self._maybe_push_to_journal("error", context, message)

    @property
    def state(self):
        return self._state

    def update_state(self, state):
        self._state = state
        write_file(self.state_path("server-state"), state.name)
        self.state_event.set()
        self.state_event.clear()

    def note_file_for_apport(self, key, path):
        self.error_reporter.note_file_for_apport(key, path)

    def note_data_for_apport(self, key, value):
        self.error_reporter.note_data_for_apport(key, value)

    def make_apport_report(
        self, kind: ErrorReportKind, thing, *, wait=False, **kw
    ) -> ErrorReport:
        return self.error_reporter.make_apport_report(kind, thing, wait=wait, **kw)

    async def _run_error_cmds(self, report: Optional[ErrorReport] = None) -> None:
        if report is not None and report._info_task is not None:
            await report._info_task
        Error = getattr(self.controllers, "Error", None)
        if Error is not None and Error.cmds:
            try:
                await Error.run()
            except Exception:
                log.exception("running error-commands failed")
        if not self.interactive:
            self.update_state(ApplicationState.ERROR)

    def _exception_handler(self, loop, context):
        exc: Optional[Exception] = context.get("exception")
        if exc is None:
            super()._exception_handler(loop, context)
            return
        log.error("top level error", exc_info=exc)

        # Some common errors have apport reports written closer to where the
        # exception was originally thrown. We write a generic "unknown error"
        # report for cases where it wasn't written already, except in cases
        # where we want to explicitly supress report generation (e.g., bad
        # autoinstall cases).

        report: Optional[ErrorReport] = None

        if isinstance(exc, NonReportableException):
            self.nonreportable_error = NonReportableError.from_exception(exc)
        else:
            report = self.error_reporter.report_for_exc(exc)
            if report is None:
                report = self.make_apport_report(
                    ErrorReportKind.UNKNOWN, "unknown error", exc=exc
                )

        self.fatal_error = report
        if self.interactive:
            self.update_state(ApplicationState.ERROR)
        if not self.running_error_commands:
            self.running_error_commands = True
            run_bg_task(self._run_error_cmds(report))

    @web.middleware
    async def middleware(self, request, handler):
        override_status = None
        controller = await controller_for_request(request)
        if isinstance(controller, SubiquityController):
            if request.headers.get("x-make-view-request") == "yes":
                if not controller.interactive():
                    override_status = "skip"
                elif self.state == ApplicationState.NEEDS_CONFIRMATION:
                    if self.base_model.is_postinstall_only(controller.model_name):
                        override_status = "confirm"
        if override_status is not None:
            resp = web.Response(headers={"x-status": override_status})
        else:
            resp = await handler(request)
        if self.updated:
            resp.headers["x-updated"] = "yes"
        else:
            resp.headers["x-updated"] = "no"
        if resp.get("exception"):
            exc = resp["exception"]
            log.debug(
                "request to %s failed with status %d: %s",
                request.raw_path,
                resp.status,
                resp.headers["x-error-msg"],
                exc_info=exc,
            )
            if isinstance(exc, NonReportableException):
                pass
            elif isinstance(exc, RecoverableError) and not exc.produce_crash_report:
                pass
            else:
                report = self.make_apport_report(
                    ErrorReportKind.SERVER_REQUEST_FAIL,
                    "request to {}".format(request.raw_path),
                    exc=exc,
                )
                resp.headers["x-error-report"] = to_json(ErrorReportRef, report.ref())
        return resp

    @with_context()
    async def apply_autoinstall_config(self, context):
        for controller in self.controllers.instances:
            if controller.interactive():
                log.debug(
                    "apply_autoinstall_config: skipping %s as interactive",
                    controller.name,
                )
                continue
            await controller.apply_autoinstall_config()
            await controller.configured()

    def filter_autoinstall(
        self,
        autoinstall_config: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Separates autoinstall config by known and unknown keys"""

        invalid_config: dict[str, Any] = copy.deepcopy(autoinstall_config)

        # Pop keys of all loaded controllers, if they exists
        for controller in self.controllers.instances:
            invalid_config.pop(controller.autoinstall_key, None)
            invalid_config.pop(controller.autoinstall_key_alias, None)

        # Pop server keys, if they exist
        for key in self.base_schema["properties"]:
            invalid_config.pop(key, None)

        valid_config: dict[str, Any] = copy.deepcopy(autoinstall_config)

        # Remove the keys we isolated
        for key in invalid_config:
            valid_config.pop(key)

        return (valid_config, invalid_config)

    @with_context(name="top_level_keys")
    def _enforce_top_level_keys(
        self,
        *,
        autoinstall_config: dict[str, Any],
        context: Context,
    ) -> dict[str, Any]:
        """Enforces usage of known top-level keys.

        In Autoinstall v1, unknown top-level keys are removed from
        the config and a cleaned config is returned.

        In Autoinstall v2, unknown top-level keys result in a fatal
        AutoinstallValidationError

        Only checks for unrecognized keys, doesn't validate them.
        Requires a version number, so this should be called after
        validating against the schema.

        """

        valid_config, invalid_config = self.filter_autoinstall(autoinstall_config)

        # If no bad keys, return early
        if len(invalid_config.keys()) == 0:
            return autoinstall_config

        # If the version is early enough, only warn
        version: int = autoinstall_config["version"]

        ctx = context
        if version == 1:
            # Warn then clean out bad keys and return

            for key in invalid_config:
                warning = f"Unrecognized top-level key {key!r}"
                log.warning(warning)
                ctx.warning(warning)

            warning = (
                "Unrecognized top-level keys will cause Autoinstall to "
                "throw an error in future versions."
            )
            log.warning(warning)
            ctx.warning(warning)

            return valid_config

        else:
            for key in invalid_config:
                error = f"Unrecognized top-level key {key!r}"
                log.error(error)
                ctx.error(error)

            error = "Unrecognized top-level keys are unsupported"
            log.error(error)
            ctx.error(error)

            raw_keys = (f"{key!r}" for key in invalid_config)
            details: str = f"Unrecognized top-level key(s): {', '.join(raw_keys)}"
            raise AutoinstallValidationError(
                owner="top-level keys",
                details=details,
            )

    def validate_autoinstall(self):
        with self.context.child("core_validation", level="INFO") as ctx:
            try:
                jsonschema.validate(self.autoinstall_config, self.base_schema)
            except ValidationError as original_exception:
                # SubiquityServer currently only checks for these sections
                # of autoinstall. Hardcode until we have better validation.
                section = "version or interactive-sections"
                new_exception: AutoinstallValidationError = AutoinstallValidationError(
                    section,
                )

                raise new_exception from original_exception

            # Enforce top level keys after ensuring we have a version number
            self.autoinstall_config = self._enforce_top_level_keys(
                autoinstall_config=self.autoinstall_config,
                context=ctx,
            )

    @with_context(name="read_config")
    def _read_config(self, *, cfg_path: str, context: Context) -> dict[str, Any]:
        with open(cfg_path) as fp:
            config: dict[str, Any] = yaml.safe_load(fp)

        autoinstall_config: dict[str, Any]

        # Support "autoinstall" as a top-level key
        if "autoinstall" in config:
            autoinstall_config = config.pop("autoinstall")

            # but the only top level key
            if len(config) != 0:
                self.interactive = bool(autoinstall_config.get("interactive-sections"))
                msg: str = (
                    "autoinstall.yaml is not a valid cloud config datasource.\n"
                    "No other keys may be present alongside 'autoinstall' at "
                    "the top level."
                )
                context.error(msg)
                raise AutoinstallValidationError(
                    owner="top-level keys",
                    details="autoinstall.yaml is not a valid cloud config datasource",
                )

        else:
            autoinstall_config = config

        return autoinstall_config

    @with_context()
    def load_autoinstall_config(self, *, only_early, context):
        log.debug(
            "load_autoinstall_config only_early %s file %s",
            only_early,
            self.autoinstall,
        )

        # Set the interactivity as early as possible so autoinstall validation
        # errors can be shown to the user in an interactive way, if applicable.
        #
        # In the case of no autoinstall data, we set interactive=true.
        #
        # Otherwise, we need to check the interactivity of the session on both
        # calls (early=True and early=False) because it's possible that an
        # early command mutates the autoinstall and changes the value of
        # interactive-sections.

        if not self.autoinstall:
            self.interactive = True
            return

        self.autoinstall_config = self._read_config(
            cfg_path=self.autoinstall, context=context
        )

        # Check every time
        self.interactive = bool(self.autoinstall_config.get("interactive-sections"))

        if only_early:
            self.controllers.Reporting.setup_autoinstall()
            self.controllers.Reporting.start()
            self.controllers.Integrity.setup_autoinstall()
            self.controllers.Integrity.start()
            self.controllers.Error.setup_autoinstall()
            self.validate_autoinstall()
            self.controllers.Early.setup_autoinstall()
        else:
            for controller in self.controllers.instances:
                controller.setup_autoinstall()

    async def start_api_server(self):
        app = web.Application(middlewares=[self.middleware])
        bind(app.router, API.meta, MetaController(self))
        bind(app.router, API.errors, ErrorController(self))
        if self.opts.dry_run:
            from .dryrun import DryRunController

            bind(app.router, API.dry_run, DryRunController(self))
        for controller in self.controllers.instances:
            controller.add_routes(app)
        runner = web.AppRunner(app, keepalive_timeout=0xFFFFFFFF, access_log=None)
        await runner.setup()
        site = web.UnixSite(runner, self.opts.socket)
        await site.start()
        # It is intended that a non-root client can connect.
        os.chmod(self.opts.socket, 0o666)

    def base_relative(self, path):
        return os.path.join(self.base_model.root, path)

    @with_context(name="extract_autoinstall")
    async def _extract_autoinstall_from_cloud_config(
        self,
        *,
        cloud_cfg: dict[str, Any],
        context: Context,
    ) -> dict[str, Any]:
        """Extract autoinstall passed via cloud config."""

        # Not really is-install-context but set to force event reporting
        context.set("is-install-context", True)
        context.enter()  # publish start event

        try:
            await validate_cloud_init_top_level_keys()
        except CloudInitSchemaTopLevelKeyError as exc:
            bad_keys: list[str] = exc.keys
            raw_keys: list[str] = [f"{key!r}" for key in bad_keys]
            context.warning(
                f"cloud-init schema validation failure for: {', '.join(raw_keys)}",
                log=log,
            )

            # Use filter_autoinstall on bad_keys to find potential autoinstall
            # keys as the cause of the schema validation error. If so,
            # raise AutoinstallError; else continue.
            #
            # Intentionally not attempting to extract bad key data since it is
            # not guaranteed that the offending keys will be top-level (or
            # even in?) in the combined config. Although still constructing
            # a dict since filter_autoinstall expects a dict.
            # LP: #2062988

            potential_autoinstall: dict[str, None] = dict(
                ((key, None) for key in bad_keys)
            )
            autoinstall, other = self.filter_autoinstall(potential_autoinstall)

            if len(autoinstall) != 0:
                for key in autoinstall:
                    context.error(
                        message=(
                            f"{key!r} is valid autoinstall but not "
                            "found under 'autoinstall'."
                        ),
                        log=log,
                    )

                raise AutoinstallError(
                    (
                        "Misplaced autoinstall directives resulted in a cloud-init "
                        "schema validation failure."
                    )
                ) from exc

            else:
                log.debug(
                    "No autoinstall keys found among bad cloud config. Continuing."
                )

        cfg: dict[str, Any] = cloud_cfg.get("autoinstall", {})

        return cfg

    @with_context()
    async def load_cloud_config(self, *, context: Context):
        # cloud-init 23.3 introduced combined-cloud-config, which helps to
        # prevent subiquity from having to go load cloudinit modules.
        # This matters because a downgrade pickle deserialization issue may
        # occur when the cloud-init outside the snap (which writes the pickle
        # data) is newer than the one inside the snap (which reads the pickle
        # data if we do stages.Init()).  LP: #2022102

        # The stages.Init() code path should be retained until we can assume a
        # minimum cloud-init version of 23.3 (when Subiquity drops support for
        # Ubuntu 22.04.2 LTS and earlier, presumably)

        cloud_cfg = get_host_combined_cloud_config()
        if len(cloud_cfg) > 0:
            system_info = cloud_cfg.get("system_info", {})
            default_user = system_info.get("default_user", {})
            self.installer_user_name = default_user.get("name")

        else:
            log.debug("loading cloud-config from stages.Init()")

            cloud_cfg, self.installer_user_name = await legacy_cloud_init_extract()

        autoinstall = await self._extract_autoinstall_from_cloud_config(
            cloud_cfg=cloud_cfg, context=context
        )

        if autoinstall != {}:
            log.debug("autoinstall found in cloud-config")
            target = self.base_relative(cloud_autoinstall_path)

            ai_yaml: str = yaml.dump(
                autoinstall,
                line_break="\n",
                indent=4,
                explicit_start=True,
                explicit_end=True,
                default_flow_style=False,
                Dumper=yaml.dumper.SafeDumper,
            )

            write_file(target, ai_yaml)
        else:
            log.debug("no autoinstall found in cloud-config")

    async def wait_for_cloudinit(self):
        if self.opts.dry_run:
            self.cloud_init_ok = True
            return

        ci_start = time.time()
        self.cloud_init_ok, status = await cloud_init_status_wait()
        log.debug("waited %ss for cloud-init", time.time() - ci_start)
        log.debug("cloud-init status: %r", status)
        if self.cloud_init_ok:
            if "disabled" in status:
                log.debug("Skip cloud-init autoinstall, cloud-init is disabled")
            else:
                await self.load_cloud_config()

    def select_autoinstall(self):
        # precedence
        # 1. command line argument autoinstall
        # 2. kernel command line argument subiquity.autoinstallpath
        # 3. autoinstall at root of drive
        # 4. autoinstall supplied by cloud config
        # 5. autoinstall baked into the iso, found at /cdrom/autoinstall.yaml

        # if opts.autoinstall is set and empty, that means
        # autoinstall has been explicitly disabled.
        if self.opts.autoinstall == "":
            return None
        if self.opts.autoinstall is not None and not os.path.exists(
            self.opts.autoinstall
        ):
            raise Exception(f"Autoinstall argument {self.opts.autoinstall} not found")

        kernel_install_path = self.kernel_cmdline.get("subiquity.autoinstallpath", None)

        locations = (
            self.opts.autoinstall,
            kernel_install_path,
            self.base_relative(root_autoinstall_path),
            self.base_relative(cloud_autoinstall_path),
            self.base_relative(iso_autoinstall_path),
        )

        for loc in locations:
            if loc is not None and os.path.exists(loc):
                break
        else:
            return None

        rootpath = self.base_relative(root_autoinstall_path)
        copy_file_if_exists(loc, rootpath)
        return rootpath

    def _user_has_password(self, username):
        with open("/etc/shadow") as fp:
            for line in fp:
                if line.startswith(username + ":$"):
                    return True
        return False

    def set_installer_password(self):
        if self.installer_user_name is None:
            # there was no default user or cloud-init was disabled.
            return

        passfile = self.state_path("installer-user-passwd")

        if os.path.exists(passfile):
            with open(passfile) as fp:
                contents = fp.read()
            self.installer_user_passwd_kind = PasswordKind.KNOWN
            self.installer_user_name, self.installer_user_passwd = contents.split(
                ":", 1
            )
            return

        def use_passwd(passwd):
            self.installer_user_passwd = passwd
            self.installer_user_passwd_kind = PasswordKind.KNOWN
            with open(passfile, "w") as fp:
                fp.write(self.installer_user_name + ":" + passwd)

        if self.opts.dry_run:
            self.installer_user_name = os.environ["USER"]
            use_passwd(rand_user_password())
            return

        username = self.installer_user_name

        if self._user_has_password(username):
            # Was the password set to a random password by a version of
            # cloud-init that records the username in the log?  (This is the
            # case we hit on upgrading the subiquity snap)
            passwd = get_installer_password_from_cloudinit_log()
            if passwd:
                use_passwd(passwd)
            else:
                self.installer_user_passwd_kind = PasswordKind.UNKNOWN
        elif not user_key_fingerprints(username):
            passwd = rand_user_password()
            cp = run_command("chpasswd", input=username + ":" + passwd + "\n")
            if cp.returncode == 0:
                use_passwd(passwd)
            else:
                log.info("setting installer password failed %s", cp)
                self.installer_user_passwd_kind = PasswordKind.NONE
        else:
            self.installer_user_passwd_kind = PasswordKind.NONE

    async def start(self):
        self.controllers.load_all()
        await self.start_api_server()
        self.update_state(ApplicationState.CLOUD_INIT_WAIT)
        await self.wait_for_cloudinit()
        self.set_installer_password()
        self.autoinstall = self.select_autoinstall()
        self.load_autoinstall_config(only_early=True)
        if self.autoinstall_config and self.controllers.Early.cmds:
            stamp_file = self.state_path("early-commands")
            if not os.path.exists(stamp_file):
                self.update_state(ApplicationState.EARLY_COMMANDS)
                # Just wait a second for any clients to get ready to print
                # output.
                await asyncio.sleep(1)
                await self.controllers.Early.run()
                open(stamp_file, "w").close()
                await asyncio.sleep(1)
        self.load_autoinstall_config(only_early=False)
        if not self.interactive and not self.opts.dry_run:
            open("/run/casper-no-prompt", "w").close()
        self.load_serialized_state()
        self.update_state(ApplicationState.WAITING)
        await super().start()
        await self.apply_autoinstall_config()

    def exit(self):
        self.update_state(ApplicationState.EXITED)
        super().exit()

    def _network_change(self):
        if not self.snapd:
            return
        self.hub.broadcast(InstallerChannels.SNAPD_NETWORK_CHANGE)

    async def _proxy_set(self):
        if not self.snapd:
            return
        await run_in_thread(
            self.snapd.connection.configure_proxy, self.base_model.proxy
        )
        self.hub.broadcast(InstallerChannels.SNAPD_NETWORK_CHANGE)

    def restart(self):
        if not self.snapd:
            return
        cmdline = ["snap", "run", "subiquity.subiquity-server"]
        if self.opts.dry_run:
            cmdline = [
                sys.executable,
                "-m",
                "subiquity.cmd.server",
            ] + sys.argv[1:]
        os.execvp(cmdline[0], cmdline)

    def make_autoinstall(self):
        config = {"version": 1}
        for controller in self.controllers.instances:
            controller_conf = controller.make_autoinstall()
            if controller_conf:
                config[controller.autoinstall_key] = controller_conf
        return config
