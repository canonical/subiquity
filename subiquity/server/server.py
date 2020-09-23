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

import logging
import os
import sys

from aiohttp import web

from subiquitycore.core import Application

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
    ErrorReportRef,
    )
from subiquity.server.controller import SubiquityController
from subiquity.server.errors import ErrorController


log = logging.getLogger('subiquity.server.server')


class MetaController:

    def __init__(self, app):
        self.app = app
        self.context = app.context.child("Meta")

    async def status_GET(self) -> ApplicationState:
        return self.app.status

    async def restart_POST(self) -> None:
        self.app.restart()


class SubiquityServer(Application):

    project = "subiquity"
    from subiquity.server import controllers as controllers_mod
    controllers = []

    def make_model(self):
        return None

    def __init__(self, opts):
        super().__init__(opts)
        self.status = ApplicationState.STARTING
        self.server_proc = None
        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root)

    def note_file_for_apport(self, key, path):
        self.error_reporter.note_file_for_apport(key, path)

    def note_data_for_apport(self, key, value):
        self.error_reporter.note_data_for_apport(key, value)

    def make_apport_report(self, kind, thing, *, wait=False, **kw):
        return self.error_reporter.make_apport_report(
            kind, thing, wait=wait, **kw)

    @web.middleware
    async def middleware(self, request, handler):
        if self.updated:
            updated = 'yes'
        else:
            updated = 'no'
        controller = await controller_for_request(request)
        if isinstance(controller, SubiquityController):
            if not controller.interactive():
                return web.Response(
                    headers={'x-status': 'skip', 'x-updated': updated})
            elif self.base_model.needs_confirmation(controller.model_name):
                return web.Response(
                    headers={'x-status': 'confirm', 'x-updated': updated})
        resp = await handler(request)
        resp.headers['x-updated'] = updated
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

    async def start_api_server(self):
        app = web.Application(middlewares=[self.middleware])
        bind(app.router, API.meta, MetaController(self))
        bind(app.router, API.errors, ErrorController(self))
        if self.opts.dry_run:
            from .dryrun import DryRunController
            bind(app.router, API.dry_run, DryRunController(self))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.UnixSite(runner, self.opts.socket)
        await site.start()

    async def start(self):
        await super().start()
        await self.start_api_server()

    def restart(self):
        cmdline = ['snap', 'run', 'subiquity']
        if self.opts.dry_run:
            cmdline = [
                sys.executable, '-m', 'subiquity.cmd.server',
                ] + sys.argv[1:]
        os.execvp(cmdline[0], cmdline)
