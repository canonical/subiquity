# Copyright 2015 Canonical, Ltd.
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
import contextvars
import inspect
import logging
import os
import signal
import sys
import traceback
from typing import Optional

import aiohttp

from subiquitycore.async_helpers import (
    run_in_thread,
    )
from subiquitycore.screen import is_linux_tty
from subiquitycore.tuicontroller import Skip
from subiquitycore.tui import TuiApplication
from subiquitycore.view import BaseView

from subiquity.client.controller import Confirm
from subiquity.client.keycodes import (
    DummyKeycodesFilter,
    KeyCodesFilter,
    )
from subiquity.common.api.client import make_client_for_conn
from subiquity.common.apidef import API
from subiquity.common.errorreport import (
    ErrorReporter,
    )
from subiquity.common.serialize import from_json
from subiquity.common.types import (
    ApplicationState,
    ErrorReportKind,
    ErrorReportRef,
    )
from subiquity.journald import journald_listen
from subiquity.ui.frame import SubiquityUI
from subiquity.ui.views.error import ErrorReportStretchy
from subiquity.ui.views.help import HelpMenu, ssh_help_texts
from subiquity.ui.views.installprogress import (
    InstallConfirmation,
    )
from subiquity.ui.views.welcome import (
    CloudInitFail,
    )


log = logging.getLogger('subiquity.client.client')


class Abort(Exception):
    def __init__(self, error_report_ref=None):
        self.error_report_ref = error_report_ref


DEBUG_SHELL_INTRO = _("""\
Installer shell session activated.

This shell session is running inside the installer environment.  You
will be returned to the installer when this shell is exited, for
example by typing Control-D or 'exit'.

Be aware that this is an ephemeral environment.  Changes to this
environment will not survive a reboot. If the install has started, the
installed system will be mounted at /target.""")


class SubiquityClient(TuiApplication):

    snapd_socket_path: Optional[str] = '/run/snapd.socket'

    variant: Optional[str] = None
    cmdline = ['snap', 'run', 'subiquity']
    dryrun_cmdline_module = 'subiquity.cmd.tui'

    from subiquity.client import controllers as controllers_mod
    project = "subiquity"

    def make_model(self):
        return None

    def make_ui(self):
        return SubiquityUI(self, self.help_menu)

    controllers = [
        "Serial",
        "Welcome",
        "Refresh",
        "Keyboard",
        "Source",
        "Zdev",
        "Network",
        "Proxy",
        "Mirror",
        "Refresh",
        "Filesystem",
        "Identity",
        "UbuntuAdvantage",
        "SSH",
        "Drivers",
        "SnapList",
        "Progress",
        ]

    variant_to_controllers = {}

    def __init__(self, opts):
        if is_linux_tty():
            self.input_filter = KeyCodesFilter()
        else:
            self.input_filter = DummyKeycodesFilter()

        self.help_menu = HelpMenu(self)
        super().__init__(opts)
        self.interactive = None
        self.server_updated = None
        self.restarting = False
        self.global_overlays = []

        try:
            self.our_tty = os.ttyname(0)
        except OSError:
            self.our_tty = "not a tty"

        self.conn = aiohttp.UnixConnector(self.opts.socket)

        self.in_make_view_cvar = contextvars.ContextVar(
            'in_make_view', default=False)

        def header_func():
            if self.in_make_view_cvar.get():
                return {'x-make-view-request': 'yes'}
            else:
                return None

        self.client = make_client_for_conn(API, self.conn, self.resp_hook,
                                           header_func=header_func)

        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root,
            self.client)

        self.note_data_for_apport("SnapUpdated", str(self.updated))
        self.note_data_for_apport("UsingAnswers", str(bool(self.answers)))

    async def _restart_server(self):
        log.debug("_restart_server")
        try:
            await self.client.meta.restart.POST()
        except aiohttp.ServerDisconnectedError:
            pass
        self.restart(remove_last_screen=False)

    async def _kill_fg_proc(self, remove_last_screen, restart_server):
        proc = self.fg_proc
        proc.kill()
        await proc.wait()
        self.fg_proc = None
        self.restart(remove_last_screen, restart_server)

    def restart(self, remove_last_screen=True, restart_server=False):
        log.debug(f"restart {remove_last_screen} {restart_server}")
        if self.fg_proc is not None:
            log.debug(
                "killing foreground process %s before restarting",
                self.fg_proc)
            self.restarting = True
            self.aio_loop.create_task(
                self._kill_fg_proc(remove_last_screen, restart_server))
            return
        if remove_last_screen:
            self._remove_last_screen()
        if restart_server:
            self.restarting = True
            self.ui.block_input = True
            self.aio_loop.create_task(self._restart_server())
            return
        if self.urwid_loop is not None:
            self.urwid_loop.stop()
        cmdline = self.cmdline
        if self.opts.dry_run:
            cmdline = [
                sys.executable, '-m', self.dryrun_cmdline_module,
                ] + sys.argv[1:] + ['--socket', self.opts.socket]
            if self.opts.server_pid is not None:
                cmdline.extend(['--server-pid', self.opts.server_pid])
            log.debug("restarting %r", cmdline)

        os.execvp(cmdline[0], cmdline)

    def resp_hook(self, response):
        headers = response.headers
        if 'x-updated' in headers:
            if self.server_updated is None:
                self.server_updated = headers['x-updated']
            elif self.server_updated != headers['x-updated']:
                self.restart(remove_last_screen=False)
                raise Abort
        status = headers.get('x-status')
        if status == 'skip':
            raise Skip
        elif status == 'confirm':
            raise Confirm
        if headers.get('x-error-report') is not None:
            ref = from_json(ErrorReportRef, headers['x-error-report'])
            raise Abort(ref)
        try:
            response.raise_for_status()
        except aiohttp.ClientError:
            report = self.error_reporter.make_apport_report(
                ErrorReportKind.SERVER_REQUEST_FAIL,
                "request to {}".format(response.url.path))
            raise Abort(report.ref())
        return response

    async def noninteractive_confirmation(self):
        await asyncio.sleep(1)
        yes = _('yes')
        no = _('no')
        answer = no
        print(_("Confirmation is required to continue."))
        print(_("Add 'autoinstall' to your kernel command line to avoid this"))
        print()
        prompt = "\n\n{} ({}|{})".format(
            _("Continue with autoinstall?"), yes, no)
        while answer != yes:
            print(prompt)
            answer = await run_in_thread(input)
        await self.confirm_install()

    async def _status_get(self, cur=None):
        while True:
            try:
                return await self.client.meta.status.GET(cur=cur)
            except aiohttp.ClientError:
                try:
                    fp = open(self.state_path("server-state"))
                except FileNotFoundError:
                    pass
                else:
                    with fp:
                        state = getattr(ApplicationState, fp.read(), None)
                    if state == ApplicationState.EXITED:
                        self.exit()
                await asyncio.sleep(1)

    async def noninteractive_watch_app_state(self, initial_status):
        app_status = initial_status
        confirm_task = None
        while True:
            app_state = app_status.state
            if app_state == ApplicationState.NEEDS_CONFIRMATION:
                if confirm_task is None:
                    confirm_task = self.aio_loop.create_task(
                        self.noninteractive_confirmation())
            elif confirm_task is not None:
                confirm_task.cancel()
                confirm_task = None
            if app_state == ApplicationState.ERROR:
                await asyncio.sleep(1)
                print("An error occurred. Press enter to start a shell")
                await run_in_thread(input)
                os.execvp("/bin/bash", ["/bin/bash"])
            app_status = await self._status_get(app_state)

    def subiquity_event_noninteractive(self, event):
        if event['SUBIQUITY_EVENT_TYPE'] == 'start':
            print('start: ' + event["MESSAGE"])
        elif event['SUBIQUITY_EVENT_TYPE'] == 'finish':
            print('finish: ' + event["MESSAGE"])

    async def connect(self):

        def p(s):
            print(s, end='', flush=True)

        async def spin(message):
            p(message + '...  ')
            while True:
                for t in ['-', '\\', '|', '/']:
                    p('\x08' + t)
                    await asyncio.sleep(0.5)

        async def spinning_wait(message, task):
            spinner = self.aio_loop.create_task(spin(message))
            try:
                return await task
            finally:
                spinner.cancel()
                p('\x08 \n')

        status = await spinning_wait("connecting", self._status_get())
        journald_listen(
            self.aio_loop,
            [status.echo_syslog_id],
            lambda e: print(e['MESSAGE']))
        if status.state == ApplicationState.STARTING_UP:
            status = await spinning_wait(
                "starting up", self._status_get(cur=status.state))
        if status.state == ApplicationState.CLOUD_INIT_WAIT:
            status = await spinning_wait(
                "waiting for cloud-init", self._status_get(cur=status.state))
        if status.state == ApplicationState.EARLY_COMMANDS:
            print("running early commands")
            status = await self._status_get(cur=status.state)
            await asyncio.sleep(0.5)
        return status

    async def start(self):
        status = await self.connect()
        self.interactive = status.interactive
        if self.interactive:
            if self.opts.ssh:
                ssh_info = await self.client.meta.ssh_info.GET()
                texts = ssh_help_texts(ssh_info)
                for line in texts:
                    import urwid
                    if isinstance(line, urwid.Widget):
                        line = '\n'.join([
                            line.decode('utf-8').rstrip()
                            for line in line.render((1000,)).text
                            ])
                    print(line)
                return

            # Get the variant from the server and reload desired
            # controllers if an override exists
            variant = await self.client.meta.client_variant.GET()
            if variant != self.variant:
                self.variant = variant
                controllers = self.variant_to_controllers.get(variant)
                if controllers:
                    self.load_controllers(controllers)

            await super().start()
            # Progress uses systemd to collect and display the installation
            # logs. Although some system don't have systemd, so we disable
            # the progress page
            if hasattr(self.controllers, "Progress"):
                journald_listen(
                    self.aio_loop,
                    [status.event_syslog_id],
                    self.controllers.Progress.event)
                journald_listen(
                    self.aio_loop,
                    [status.log_syslog_id],
                    self.controllers.Progress.log_line)
            if not status.cloud_init_ok:
                self.add_global_overlay(CloudInitFail(self))
            self.error_reporter.load_reports()
            for report in self.error_reporter.reports:
                if report.kind == ErrorReportKind.UI and not report.seen:
                    self.show_error_report(report.ref())
                    break
        else:
            if self.opts.run_on_serial:
                # Thanks to the fact that we are launched with agetty's
                # --skip-login option, on serial lines we can end up starting
                # with some strange terminal settings (see the docs for
                # --skip-login in agetty(8)). For an interactive install this
                # does not matter as the settings will soon be clobbered but
                # for a non-interactive one we need to clear things up or the
                # prompting for confirmation will be confusing.
                os.system('stty sane')
            journald_listen(
                self.aio_loop,
                [status.event_syslog_id],
                self.subiquity_event_noninteractive,
                seek=True)
            self.aio_loop.create_task(
                self.noninteractive_watch_app_state(status))

    def _exception_handler(self, loop, context):
        exc = context.get('exception')
        if self.restarting:
            log.debug('ignoring %s %s during restart', exc, type(exc))
            return
        if isinstance(exc, Abort):
            if self.interactive:
                self.show_error_report(exc.error_report_ref)
                return
        super()._exception_handler(loop, context)

    def extra_urwid_loop_args(self):
        return dict(input_filter=self.input_filter.filter)

    def run(self):
        try:
            super().run()
        except Exception:
            print("generating crash report")
            try:
                report = self.make_apport_report(
                    ErrorReportKind.UI, "Installer UI", interrupt=False,
                    wait=True)
                if report is not None:
                    print("report saved to {path}".format(path=report.path))
            except Exception:
                print("report generation failed")
                traceback.print_exc()
            if self.interactive:
                self._remove_last_screen()
                raise
            else:
                traceback.print_exc()
                signal.pause()
        finally:
            if self.opts.server_pid:
                print('killing server {}'.format(self.opts.server_pid))
                pid = int(self.opts.server_pid)
                os.kill(pid, 2)
                os.waitpid(pid, 0)

    async def confirm_install(self):
        await self.client.meta.confirm.POST(self.our_tty)

    def add_global_overlay(self, overlay):
        self.global_overlays.append(overlay)
        if isinstance(self.ui.body, BaseView):
            self.ui.body.show_stretchy_overlay(overlay)

    def remove_global_overlay(self, overlay):
        if overlay in self.global_overlays:
            self.global_overlays.remove(overlay)
        if isinstance(self.ui.body, BaseView):
            self.ui.body.remove_overlay(overlay)

    def _remove_last_screen(self):
        last_screen = self.state_path('last-screen')
        if os.path.exists(last_screen):
            os.unlink(last_screen)

    def exit(self):
        self._remove_last_screen()
        super().exit()

    def select_initial_screen(self):
        last_screen = None
        if self.updated:
            state_path = self.state_path('last-screen')
            if os.path.exists(state_path):
                with open(state_path) as fp:
                    last_screen = fp.read().strip()
        index = 0
        if last_screen:
            for i, controller in enumerate(self.controllers.instances):
                if controller.name == last_screen:
                    index = i
        self.aio_loop.create_task(self._select_initial_screen(index))

    async def _select_initial_screen(self, index):
        endpoint_names = []
        for c in self.controllers.instances[:index]:
            if c.endpoint_name:
                endpoint_names.append(c.endpoint_name)
        if endpoint_names:
            await self.client.meta.mark_configured.POST(endpoint_names)
        if self.variant:
            await self.client.meta.client_variant.POST(self.variant)
        self.controllers.index = index - 1
        self.next_screen()

    async def move_screen(self, increment, coro):
        try:
            await super().move_screen(increment, coro)
        except Confirm:
            self.show_confirm_install()

    def show_confirm_install(self):
        log.debug("showing InstallConfirmation over %s", self.ui.body)
        self.add_global_overlay(InstallConfirmation(self))

    async def _start_answers_for_view(self, controller, view):
        # The view returned by make_view_for_controller is not always shown
        # immediately (if progress is being shown, but has not yet been shown
        # for a full second) so wait until it is before starting the answers.
        while self.ui.body is not view:
            await asyncio.sleep(0.1)
        coro = controller.run_answers()
        if inspect.iscoroutine(coro):
            await coro

    async def make_view_for_controller(self, new):
        tok = self.in_make_view_cvar.set(True)
        try:
            view = await super().make_view_for_controller(new)
        finally:
            self.in_make_view_cvar.reset(tok)
        if new.answers:
            self.aio_loop.create_task(self._start_answers_for_view(new, view))
        with open(self.state_path('last-screen'), 'w') as fp:
            fp.write(new.name)
        return view

    def show_progress(self):
        if hasattr(self.controllers, 'Progress'):
            self.ui.set_body(self.controllers.Progress.progress_view)

    def unhandled_input(self, key):
        if key == 'f1':
            if not self.ui.right_icon.current_help:
                self.ui.right_icon.open_pop_up()
        elif key in ['ctrl z', 'f2']:
            self.debug_shell()
        elif self.opts.dry_run:
            self.unhandled_input_dry_run(key)
        else:
            super().unhandled_input(key)

    def unhandled_input_dry_run(self, key):
        if key in ['ctrl e', 'ctrl r']:
            interrupt = key == 'ctrl e'
            try:
                1/0
            except ZeroDivisionError:
                self.make_apport_report(
                    ErrorReportKind.UNKNOWN, "example", interrupt=interrupt)
        elif key == 'ctrl u':
            1/0
        elif key == 'ctrl b':
            self.aio_loop.create_task(self.client.dry_run.crash.GET())
        else:
            super().unhandled_input(key)

    def debug_shell(self, after_hook=None):

        def _before():
            os.system("clear")
            print(DEBUG_SHELL_INTRO)

        self.run_command_in_foreground(
            ["bash"], before_hook=_before, after_hook=after_hook, cwd='/')

    def note_file_for_apport(self, key, path):
        self.error_reporter.note_file_for_apport(key, path)

    def note_data_for_apport(self, key, value):
        self.error_reporter.note_data_for_apport(key, value)

    def make_apport_report(self, kind, thing, *, interrupt, wait=False, **kw):
        report = self.error_reporter.make_apport_report(
            kind, thing, wait=wait, **kw)

        if report is not None and interrupt:
            self.show_error_report(report.ref())

        return report

    def show_error_report(self, error_ref):
        log.debug("show_error_report %r", error_ref.base)
        if isinstance(self.ui.body, BaseView):
            w = getattr(self.ui.body._w, 'stretchy', None)
            if isinstance(w, ErrorReportStretchy):
                # Don't show an error if already looking at one.
                return
        self.add_global_overlay(ErrorReportStretchy(self, error_ref))
