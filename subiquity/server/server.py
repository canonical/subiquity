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
import logging
import os
import shlex
import sys
import time
from typing import List, Optional

from aiohttp import web

from cloudinit import safeyaml, stages
from cloudinit.config.cc_set_passwords import rand_user_password
from cloudinit.distros import ug_util

import jsonschema

from systemd import journal

import yaml

from subiquitycore.async_helpers import run_in_thread
from subiquitycore.context import with_context
from subiquitycore.core import Application
from subiquitycore.file_util import write_file
from subiquitycore.prober import Prober
from subiquitycore.ssh import (
    host_key_fingerprints,
    user_key_fingerprints,
    )
from subiquitycore.utils import arun_command, run_command

from subiquity.common.api.server import (
    bind,
    controller_for_request,
    )
from subiquity.common.apidef import API
from subiquity.common.errorreport import (
    ErrorReportKind,
    ErrorReporter,
    )
from subiquity.common.serialize import to_json
from subiquity.common.types import (
    ApplicationState,
    ApplicationStatus,
    ErrorReportRef,
    KeyFingerprint,
    LiveSessionSSHInfo,
    PasswordKind,
    )
from subiquity.models.subiquity import (
    ModelNames,
    SubiquityModel,
    )
from subiquity.server.controller import SubiquityController
from subiquity.server.geoip import (
    GeoIP,
    DryRunGeoIPStrategy,
    HTTPGeoIPStrategy,
    )
from subiquity.server.errors import ErrorController
from subiquity.server.runner import get_command_runner
from subiquity.server.types import InstallerChannels
from subiquitycore.snapd import (
    AsyncSnapd,
    FakeSnapdConnection,
    SnapdConnection,
    )

NOPROBERARG = "NOPROBER"

log = logging.getLogger('subiquity.server.server')


class MetaController:

    def __init__(self, app):
        self.app = app
        self.context = app.context.child("Meta")
        self.free_only = False

    async def status_GET(self, cur: Optional[ApplicationState] = None) \
            -> ApplicationStatus:
        if cur == self.app.state:
            await self.app.state_event.wait()
        return ApplicationStatus(
            state=self.app.state,
            confirming_tty=self.app.confirming_tty,
            error=self.app.fatal_error,
            cloud_init_ok=self.app.cloud_init_ok,
            interactive=self.app.interactive,
            echo_syslog_id=self.app.echo_syslog_id,
            event_syslog_id=self.app.event_syslog_id,
            log_syslog_id=self.app.log_syslog_id)

    async def confirm_POST(self, tty: str) -> None:
        self.app.confirming_tty = tty
        self.app.base_model.confirm()

    async def restart_POST(self) -> None:
        self.app.restart()

    async def mark_configured_POST(self, endpoint_names: List[str]) -> None:
        endpoints = {getattr(API, en, None) for en in endpoint_names}
        for controller in self.app.controllers.instances:
            if controller.endpoint in endpoints:
                await controller.configured()

    async def client_variant_POST(self, variant: str) -> None:
        if variant not in self.app.supported_variants:
            raise ValueError(f'unrecognized client variant {variant}')
        from subiquity.models.source import fake_entries
        if variant in fake_entries:
            if self.app.base_model.source.current.variant != variant:
                self.app.base_model.source.current = fake_entries[variant]
            await self.app.controllers.Source.configured()
        else:
            self.app.base_model.set_source_variant(variant)
        self.app.set_source_variant(variant)

    async def client_variant_GET(self) -> str:
        return self.app.variant

    async def ssh_info_GET(self) -> Optional[LiveSessionSSHInfo]:
        ips = []
        if self.app.base_model.network:
            for dev in self.app.base_model.network.get_all_netdevs():
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
            host_key_fingerprints=host_fingerprints)

    async def free_only_GET(self) -> bool:
        return self.free_only

    async def free_only_POST(self, enable: bool) -> None:
        self.free_only = enable
        to_disable = {'restricted', 'multiverse'}
        # enabling free only mode means disabling components
        self.app.base_model.mirror.disable_components(to_disable, enable)


def get_installer_password_from_cloudinit_log():
    try:
        fp = open("/var/log/cloud-init-output.log")
    except FileNotFoundError:
        return None

    with fp:
        for line in fp:
            if line.startswith("installer:"):
                return line[len("installer:"):].strip()

    return None


INSTALL_MODEL_NAMES = ModelNames({
    "debconf_selections",
    "filesystem",
    "kernel",
    "keyboard",
    "mirror",
    "network",
    "proxy",
    "source",
    })

POSTINSTALL_MODEL_NAMES = ModelNames({
    "drivers",
    "identity",
    "locale",
    "network",
    "packages",
    "snaplist",
    "ssh",
    "ubuntu_advantage",
    "userdata",
    },
    desktop={"timezone"})


class SubiquityServer(Application):

    snapd_socket_path = '/run/snapd.socket'

    base_schema = {
        'type': 'object',
        'properties': {
            'version': {
                'type': 'integer',
                'minimum': 1,
                'maximum': 1,
                },
            },
        'required': ['version'],
        'additionalProperties': True,
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
        "Keyboard",
        "Zdev",
        "Source",
        "Network",
        "UbuntuAdvantage",
        "Proxy",
        "Mirror",
        "Filesystem",
        "Identity",
        "SSH",
        "SnapList",
        "Drivers",
        "TimeZone",
        "Install",
        "Updates",
        "Late",
        "Shutdown",
        ]

    supported_variants = ["server", "desktop"]

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath(self.opts.output_base)
        return SubiquityModel(
            root, self.hub, INSTALL_MODEL_NAMES, POSTINSTALL_MODEL_NAMES)

    def __init__(self, opts, block_log_dir):
        super().__init__(opts)
        self.set_source_variant(self.supported_variants[0])
        self.block_log_dir = block_log_dir
        self.cloud = None
        self.cloud_init_ok = None
        self.state_event = asyncio.Event()
        self.update_state(ApplicationState.STARTING_UP)
        self.interactive = None
        self.confirming_tty = ''
        self.fatal_error = None
        self.running_error_commands = False
        self.installer_user_name = None
        self.installer_user_passwd_kind = PasswordKind.NONE
        self.installer_user_passwd = None

        self.echo_syslog_id = 'subiquity_echo.{}'.format(os.getpid())
        self.event_syslog_id = 'subiquity_event.{}'.format(os.getpid())
        self.log_syslog_id = 'subiquity_log.{}'.format(os.getpid())
        self.command_runner = get_command_runner(self)

        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root)
        if opts.machine_config == NOPROBERARG:
            self.prober = None
        else:
            self.prober = Prober(opts.machine_config, self.debug_flags)
        self.kernel_cmdline = shlex.split(opts.kernel_cmdline)
        if opts.snaps_from_examples:
            connection = FakeSnapdConnection(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(
                            os.path.dirname(__file__))),
                    "examples", "snaps"),
                self.scale_factor, opts.output_base)
            self.snapd = AsyncSnapd(connection)
        elif os.path.exists(self.snapd_socket_path):
            connection = SnapdConnection(self.root, self.snapd_socket_path)
            self.snapd = AsyncSnapd(connection)
        else:
            log.info("no snapd socket found. Snap support is disabled")
            self.snapd = None
        self.note_data_for_apport("SnapUpdated", str(self.updated))
        self.event_listeners = []
        self.autoinstall_config = None
        self.hub.subscribe(InstallerChannels.NETWORK_UP, self._network_change)
        self.hub.subscribe(InstallerChannels.NETWORK_PROXY_SET,
                           self._proxy_set)
        if self.opts.dry_run:
            geoip_strategy = DryRunGeoIPStrategy()
        else:
            geoip_strategy = HTTPGeoIPStrategy()

        self.geoip = GeoIP(self, strategy=geoip_strategy)

    def set_source_variant(self, variant):
        self.variant = variant

    def load_serialized_state(self):
        for controller in self.controllers.instances:
            controller.load_state()

    def add_event_listener(self, listener):
        self.event_listeners.append(listener)

    def _maybe_push_to_journal(self, event_type, context, description):
        if not context.get('is-install-context') and \
          self.interactive in [True, None]:
            controller = context.get('controller')
            if controller is None or controller.interactive():
                return
        if context.get('request'):
            return
        indent = context.full_name().count('/') - 2
        if context.get('is-install-context') and self.interactive:
            indent -= 1
            msg = context.description
        else:
            msg = context.full_name()
            if description:
                msg += ': ' + description
        msg = '  ' * indent + msg
        if context.parent:
            parent_id = str(context.parent.id)
        else:
            parent_id = ''
        journal.send(
            msg,
            PRIORITY=context.level,
            SYSLOG_IDENTIFIER=self.event_syslog_id,
            SUBIQUITY_CONTEXT_NAME=context.full_name(),
            SUBIQUITY_EVENT_TYPE=event_type,
            SUBIQUITY_CONTEXT_ID=str(context.id),
            SUBIQUITY_CONTEXT_PARENT_ID=parent_id)

    def report_start_event(self, context, description):
        for listener in self.event_listeners:
            listener.report_start_event(context, description)
        self._maybe_push_to_journal('start', context, description)

    def report_finish_event(self, context, description, status):
        for listener in self.event_listeners:
            listener.report_finish_event(context, description, status)
        self._maybe_push_to_journal('finish', context, description)

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

    def make_apport_report(self, kind, thing, *, wait=False, **kw):
        return self.error_reporter.make_apport_report(
            kind, thing, wait=wait, **kw)

    async def _run_error_cmds(self, report):
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
        exc = context.get('exception')
        if exc is None:
            super()._exception_handler(loop, context)
            return
        report = self.error_reporter.report_for_exc(exc)
        log.error("top level error", exc_info=exc)
        if not report:
            report = self.make_apport_report(
                ErrorReportKind.UNKNOWN, "unknown error",
                exc=exc)
        self.fatal_error = report
        if self.interactive:
            self.update_state(ApplicationState.ERROR)
        if not self.running_error_commands:
            self.running_error_commands = True
            self.aio_loop.create_task(self._run_error_cmds(report))

    @web.middleware
    async def middleware(self, request, handler):
        override_status = None
        controller = await controller_for_request(request)
        if isinstance(controller, SubiquityController):
            if not controller.interactive():
                override_status = 'skip'
            elif (self.state == ApplicationState.NEEDS_CONFIRMATION and
                  request.headers.get('x-make-view-request') == 'yes'):
                if self.base_model.is_postinstall_only(controller.model_name):
                    override_status = 'confirm'
        if override_status is not None:
            resp = web.Response(headers={'x-status': override_status})
        else:
            resp = await handler(request)
        if self.updated:
            resp.headers['x-updated'] = 'yes'
        else:
            resp.headers['x-updated'] = 'no'
        if resp.get('exception'):
            exc = resp['exception']
            log.debug(
                'request to {} crashed'.format(request.raw_path), exc_info=exc)
            report = self.make_apport_report(
                ErrorReportKind.SERVER_REQUEST_FAIL,
                "request to {}".format(request.raw_path),
                exc=exc)
            resp.headers['x-error-report'] = to_json(
                ErrorReportRef, report.ref())
        return resp

    @with_context()
    async def apply_autoinstall_config(self, context):
        for controller in self.controllers.instances:
            if controller.interactive():
                log.debug(
                    "apply_autoinstall_config: skipping %s as interactive",
                    controller.name)
                continue
            await controller.apply_autoinstall_config()
            await controller.configured()

    def load_autoinstall_config(self, *, only_early):
        log.debug("load_autoinstall_config only_early %s", only_early)
        if not self.opts.autoinstall:
            # autoinstall is None -> no autoinstall file supplied or found
            # autoinstall is empty -> explicitly disabling autoinstall
            return
        with open(self.opts.autoinstall) as fp:
            self.autoinstall_config = yaml.safe_load(fp)
        if only_early:
            self.controllers.Reporting.setup_autoinstall()
            self.controllers.Reporting.start()
            self.controllers.Error.setup_autoinstall()
            with self.context.child("core_validation", level="INFO"):
                jsonschema.validate(self.autoinstall_config, self.base_schema)
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
        runner = web.AppRunner(app, keepalive_timeout=0xffffffff)
        await runner.setup()
        site = web.UnixSite(runner, self.opts.socket)
        await site.start()
        # It is intended that a non-root client can connect.
        os.chmod(self.opts.socket, 0o666)

    async def wait_for_cloudinit(self):
        if self.opts.dry_run:
            self.cloud_init_ok = True
            return
        ci_start = time.time()
        status_coro = arun_command(["cloud-init", "status", "--wait"])
        try:
            status_cp = await asyncio.wait_for(status_coro, 600)
        except asyncio.TimeoutError:
            status_txt = '<timeout>'
            self.cloud_init_ok = False
        else:
            status_txt = status_cp.stdout
            self.cloud_init_ok = True
        log.debug("waited %ss for cloud-init", time.time() - ci_start)
        if "status: done" in status_txt:
            log.debug("loading cloud config")
            init = stages.Init()
            init.read_cfg()
            init.fetch(existing="trust")
            self.cloud = init.cloudify()
            if self.opts.autoinstall is None:
                autoinstall_path = '/autoinstall.yaml'
                if 'autoinstall' in self.cloud.cfg:
                    if not os.path.exists(autoinstall_path):
                        cfg = self.cloud.cfg['autoinstall']
                        write_file(autoinstall_path, safeyaml.dumps(cfg))
                if os.path.exists(autoinstall_path):
                    self.opts.autoinstall = autoinstall_path
        else:
            log.debug(
                "cloud-init status: %r, assumed disabled",
                status_txt)

    def _user_has_password(self, username):
        with open('/etc/shadow') as fp:
            for line in fp:
                if line.startswith(username + ":$"):
                    return True
        return False

    def set_installer_password(self):
        if self.cloud is None:
            return

        passfile = self.state_path("installer-user-passwd")

        if os.path.exists(passfile):
            with open(passfile) as fp:
                contents = fp.read()
            self.installer_user_passwd_kind = PasswordKind.KNOWN
            self.installer_user_name, self.installer_user_passwd = \
                contents.split(':', 1)
            return

        def use_passwd(passwd):
            self.installer_user_passwd = passwd
            self.installer_user_passwd_kind = PasswordKind.KNOWN
            with open(passfile, 'w') as fp:
                fp.write(self.installer_user_name + ':' + passwd)

        if self.opts.dry_run:
            self.installer_user_name = os.environ['USER']
            use_passwd(rand_user_password())
            return

        (users, _groups) = ug_util.normalize_users_groups(
            self.cloud.cfg, self.cloud.distro)
        (username, _user_config) = ug_util.extract_default(users)

        self.installer_user_name = username

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
            cp = run_command('chpasswd', input=username + ':'+passwd+'\n')
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
        self.load_autoinstall_config(only_early=True)
        if self.autoinstall_config and self.controllers.Early.cmds:
            stamp_file = self.state_path("early-commands")
            if not os.path.exists(stamp_file):
                self.update_state(ApplicationState.EARLY_COMMANDS)
                # Just wait a second for any clients to get ready to print
                # output.
                await asyncio.sleep(1)
                await self.controllers.Early.run()
                open(stamp_file, 'w').close()
                await asyncio.sleep(1)
        self.load_autoinstall_config(only_early=False)
        if self.autoinstall_config:
            self.interactive = bool(
                self.autoinstall_config.get('interactive-sections'))
        else:
            self.interactive = True
        if not self.interactive and not self.opts.dry_run:
            open('/run/casper-no-prompt', 'w').close()
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
            self.snapd.connection.configure_proxy, self.base_model.proxy)
        self.hub.broadcast(InstallerChannels.SNAPD_NETWORK_CHANGE)

    def restart(self):
        if not self.snapd:
            return
        cmdline = ['snap', 'run', 'subiquity.subiquity-server']
        if self.opts.dry_run:
            cmdline = [
                sys.executable, '-m', 'subiquity.cmd.server',
                ] + sys.argv[1:]
        os.execvp(cmdline[0], cmdline)

    def make_autoinstall(self):
        config = {'version': 1}
        for controller in self.controllers.instances:
            controller_conf = controller.make_autoinstall()
            if controller_conf:
                config[controller.autoinstall_key] = controller_conf
        return config
