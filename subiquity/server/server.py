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
from typing import List, Optional

from aiohttp import web

import jsonschema

from systemd import journal

import yaml

from subiquitycore.async_helpers import run_in_thread, schedule_task
from subiquitycore.context import with_context
from subiquitycore.core import Application
from subiquitycore.prober import Prober

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
    InstallState,
    )
from subiquity.server.controller import SubiquityController
from subiquity.models.subiquity import SubiquityModel
from subiquity.server.errors import ErrorController
from subiquitycore.snapd import (
    AsyncSnapd,
    FakeSnapdConnection,
    SnapdConnection,
    )


log = logging.getLogger('subiquity.server.server')


class MetaController:

    def __init__(self, app):
        self.app = app
        self.context = app.context.child("Meta")

    async def status_GET(self, cur: Optional[ApplicationState] = None) \
            -> ApplicationStatus:
        if cur == self.app.state:
            await self.app.state_event.wait()
        return ApplicationStatus(
            self.app.state,
            early_commands_syslog_id=self.app.early_commands_syslog_id,
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
                controller.configured()


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
        "Keyboard",
        "Zdev",
        "Network",
        "Proxy",
        "Mirror",
        "Filesystem",
        "Identity",
        "Install",
        "Late",
        ]

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SubiquityModel(root, self.opts.sources)

    def __init__(self, opts, block_log_dir):
        super().__init__(opts)
        self.block_log_dir = block_log_dir
        self._state = ApplicationState.STARTING
        self.state_event = asyncio.Event()
        self.confirming_tty = ''

        self.early_commands_syslog_id = 'subiquity_commands.{}'.format(
            os.getpid())
        self.event_syslog_id = 'subiquity_event.{}'.format(os.getpid())
        self.log_syslog_id = 'subiquity_log.{}'.format(os.getpid())

        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root)
        self.prober = Prober(opts.machine_config, self.debug_flags)
        self.kernel_cmdline = shlex.split(opts.kernel_cmdline)
        if opts.snaps_from_examples:
            connection = FakeSnapdConnection(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(
                            os.path.dirname(__file__))),
                    "examples", "snaps"),
                self.scale_factor)
        else:
            connection = SnapdConnection(self.root, self.snapd_socket_path)
        self.snapd = AsyncSnapd(connection)
        self.note_data_for_apport("SnapUpdated", str(self.updated))
        self.event_listeners = []
        self.autoinstall_config = None
        self.signal.connect_signals([
            ('network-proxy-set', lambda: schedule_task(self._proxy_set())),
            ('network-change', self._network_change),
            ])

    def load_serialized_state(self):
        for controller in self.controllers.instances:
            controller.load_state()

    def add_event_listener(self, listener):
        self.event_listeners.append(listener)

    def _maybe_push_to_journal(self, event_type, context, description):
        if not context.get('is-install-context') and self.interactive():
            controller = context.get('controller')
            if controller is None or controller.interactive():
                return
        if context.get('request'):
            return
        indent = context.full_name().count('/') - 2
        if context.get('is-install-context') and self.interactive():
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
        self.state_event.set()
        self.state_event.clear()

    def note_file_for_apport(self, key, path):
        self.error_reporter.note_file_for_apport(key, path)

    def note_data_for_apport(self, key, value):
        self.error_reporter.note_data_for_apport(key, value)

    def make_apport_report(self, kind, thing, *, wait=False, **kw):
        return self.error_reporter.make_apport_report(
            kind, thing, wait=wait, **kw)

    def interactive(self):
        if not self.autoinstall_config:
            return True
        return bool(self.autoinstall_config.get('interactive-sections'))

    @web.middleware
    async def middleware(self, request, handler):
        override_status = None
        controller = await controller_for_request(request)
        if isinstance(controller, SubiquityController):
            install_state = self.controllers.Install.install_state
            if not controller.interactive():
                override_status = 'skip'
            elif install_state == InstallState.NEEDS_CONFIRMATION:
                if self.base_model.needs_configuration(controller.model_name):
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
            controller.configured()

    def load_autoinstall_config(self, only_early):
        log.debug("load_autoinstall_config only_early %s", only_early)
        if self.opts.autoinstall is None:
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
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.UnixSite(runner, self.opts.socket)
        await site.start()

    async def start(self):
        self.controllers.load_all()
        await self.start_api_server()
        self.load_autoinstall_config(only_early=True)
        if self.autoinstall_config and self.controllers.Early.cmds:
            stamp_file = self.state_path("early-commands")
            if not os.path.exists(stamp_file):
                self.update_state(ApplicationState.EARLY_COMMANDS)
                await self.controllers.Early.run()
                open(stamp_file, 'w').close()
        self.load_autoinstall_config(only_early=False)
        if not self.interactive() and not self.opts.dry_run:
            open('/run/casper-no-prompt', 'w').close()
        self.load_serialized_state()
        if self.interactive():
            self.update_state(ApplicationState.INTERACTIVE)
        else:
            self.update_state(ApplicationState.NON_INTERACTIVE)
            await asyncio.sleep(1)
        await super().start()
        await self.apply_autoinstall_config()

    def _network_change(self):
        self.signal.emit_signal('snapd-network-change')

    async def _proxy_set(self):
        await run_in_thread(
            self.snapd.connection.configure_proxy, self.base_model.proxy)
        self.signal.emit_signal('snapd-network-change')

    def restart(self):
        cmdline = ['snap', 'run', 'subiquity']
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
