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
import logging
import os
import shlex
import signal
import sys
import traceback

import aiohttp

import jsonschema

from systemd import journal

import yaml

from subiquitycore.async_helpers import (
    run_in_thread,
    schedule_task,
    )
from subiquitycore.prober import Prober
from subiquitycore.screen import is_linux_tty
from subiquitycore.tuicontroller import Skip
from subiquitycore.tui import TuiApplication
from subiquitycore.snapd import (
    AsyncSnapd,
    FakeSnapdConnection,
    SnapdConnection,
    )
from subiquitycore.view import BaseView

from subiquity.common.api.client import make_client_for_conn
from subiquity.common.apidef import API
from subiquity.common.errorreport import (
    ErrorReporter,
    )
from subiquity.common.serialize import from_json
from subiquity.common.types import (
    ErrorReportKind,
    ErrorReportRef,
    )
from subiquity.controller import Confirm
from subiquity.journald import journald_listen
from subiquity.keycodes import (
    DummyKeycodesFilter,
    KeyCodesFilter,
    )
from subiquity.lockfile import Lockfile
from subiquity.models.subiquity import SubiquityModel
from subiquity.ui.frame import SubiquityUI
from subiquity.ui.views.error import ErrorReportStretchy
from subiquity.ui.views.help import HelpMenu


log = logging.getLogger('subiquity.core')


class Abort(Exception):
    def __init__(self, error_report_ref):
        self.error_report_ref = error_report_ref


DEBUG_SHELL_INTRO = _("""\
Installer shell session activated.

This shell session is running inside the installer environment.  You
will be returned to the installer when this shell is exited, for
example by typing Control-D or 'exit'.

Be aware that this is an ephemeral environment.  Changes to this
environment will not survive a reboot. If the install has started, the
installed system will be mounted at /target.""")


class Subiquity(TuiApplication):

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

    from subiquity import controllers as controllers_mod
    project = "subiquity"

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SubiquityModel(root, self.opts.sources)

    def make_ui(self):
        return SubiquityUI(self, self.help_menu)

    controllers = [
        "Early",
        "Reporting",
        "Error",
        "Userdata",
        "Package",
        "Debconf",
        "Welcome",
        "Refresh",
        "Keyboard",
        "Zdev",
        "Network",
        "Proxy",
        "Mirror",
        "Refresh",
        "Filesystem",
        "Identity",
        "SSH",
        "SnapList",
        "InstallProgress",
        "Late",
        "Reboot",
    ]

    def __init__(self, opts, block_log_dir):
        if is_linux_tty():
            self.input_filter = KeyCodesFilter()
        else:
            self.input_filter = DummyKeycodesFilter()

        self.help_menu = HelpMenu(self)
        super().__init__(opts)

        self.event_syslog_id = 'subiquity_event.{}'.format(os.getpid())
        self.log_syslog_id = 'subiquity_log.{}'.format(os.getpid())

        self.server_updated = None
        self.restarting_server = False
        self.prober = Prober(opts.machine_config, self.debug_flags)
        journald_listen(
            self.aio_loop, ["subiquity"], self.subiquity_event, seek=True)
        self.event_listeners = []
        self.install_lock_file = Lockfile(self.state_path("installing"))
        self.global_overlays = []
        self.block_log_dir = block_log_dir
        self.kernel_cmdline = shlex.split(opts.kernel_cmdline)
        if "noinstall" in self.kernel_cmdline:
          logging.Info("Exiting due to noinstall kernel parameter")
          sys.exit(0)
        if opts.snaps_from_examples:
            connection = FakeSnapdConnection(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(__file__)),
                    "examples", "snaps"),
                self.scale_factor)
        else:
            connection = SnapdConnection(self.root, self.snapd_socket_path)
        self.snapd = AsyncSnapd(connection)
        self.signal.connect_signals([
            ('network-proxy-set', lambda: schedule_task(self._proxy_set())),
            ('network-change', self._network_change),
            ])

        self.conn = aiohttp.UnixConnector(self.opts.socket)
        self.client = make_client_for_conn(API, self.conn, self.resp_hook)

        self.autoinstall_config = {}
        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root,
            self.client)

        self.note_data_for_apport("SnapUpdated", str(self.updated))
        self.note_data_for_apport("UsingAnswers", str(bool(self.answers)))

    def subiquity_event(self, event):
        if event["MESSAGE"] == "starting install":
            if event["_PID"] == os.getpid():
                return
            if not self.install_lock_file.is_exclusively_locked():
                return
            from subiquity.ui.views.installprogress import (
                InstallRunning,
                )
            tty = self.install_lock_file.read_content()
            install_running = InstallRunning(self.ui.body, self, tty)
            self.add_global_overlay(install_running)
            schedule_task(self._hide_install_running(install_running))

    async def _hide_install_running(self, install_running):
        # Wait until the install has completed...
        async with self.install_lock_file.shared():
            # And remove the overlay.
            self.remove_global_overlay(install_running)

    async def _restart_server(self):
        log.debug("_restart_server")
        try:
            await self.client.meta.restart.POST()
        except aiohttp.ServerDisconnectedError:
            pass
        self.restart(remove_last_screen=False)

    def restart(self, remove_last_screen=True, restart_server=False):
        log.debug(f"restart {remove_last_screen} {restart_server}")
        if remove_last_screen:
            self._remove_last_screen()
        if restart_server:
            self.restarting_server = True
            self.ui.block_input = True
            self.aio_loop.create_task(self._restart_server())
            return
        if self.urwid_loop is not None:
            self.urwid_loop.stop()
        cmdline = ['snap', 'run', 'subiquity']
        if self.opts.dry_run:
            cmdline = [
                sys.executable, '-m', 'subiquity.cmd.tui',
                ] + sys.argv[1:] + ['--socket', self.opts.socket]
            if self.opts.server_pid is not None:
                cmdline.extend(['--server-pid', self.opts.server_pid])
            log.debug("restarting %r", cmdline)

        os.execvp(cmdline[0], cmdline)

    def get_primary_tty(self):
        tty = '/dev/tty1'
        for work in self.kernel_cmdline:
            if work.startswith('console='):
                tty = '/dev/' + work[len('console='):].split(',')[0]
        return tty

    async def load_autoinstall_config(self):
        with open(self.opts.autoinstall) as fp:
            self.autoinstall_config = yaml.safe_load(fp)
        primary_tty = self.get_primary_tty()
        try:
            our_tty = os.ttyname(0)
        except OSError:
            # This is a gross hack for testing in travis.
            our_tty = "/dev/not a tty"
        if not self.interactive() and our_tty != primary_tty:
            while True:
                print(
                    _("the installer running on {tty} will perform the "
                      "autoinstall").format(tty=primary_tty))
                print()
                print(_("press enter to start a shell"))
                input()
                os.system("cd / && bash")
        self.controllers.Reporting.start()
        with self.context.child("core_validation", level="INFO"):
            jsonschema.validate(self.autoinstall_config, self.base_schema)
        self.controllers.Reporting.setup_autoinstall()
        self.controllers.Early.setup_autoinstall()
        self.controllers.Error.setup_autoinstall()
        if self.controllers.Early.cmds:
            stamp_file = self.state_path("early-commands")
            if our_tty != primary_tty:
                print(
                    _("waiting for installer running on {tty} to run early "
                      "commands").format(tty=primary_tty))
                while not os.path.exists(stamp_file):
                    await asyncio.sleep(1)
            elif not os.path.exists(stamp_file):
                await self.controllers.Early.run()
                open(stamp_file, 'w').close()
            with open(self.opts.autoinstall) as fp:
                self.autoinstall_config = yaml.safe_load(fp)
            with self.context.child("core_validation", level="INFO"):
                jsonschema.validate(self.autoinstall_config, self.base_schema)
        for controller in self.controllers.instances:
            controller.setup_autoinstall()
        if not self.interactive() and self.opts.run_on_serial:
            # Thanks to the fact that we are launched with agetty's
            # --skip-login option, on serial lines we can end up starting with
            # some strange terminal settings (see the docs for --skip-login in
            # agetty(8)). For an interactive install this does not matter as
            # the settings will soon be clobbered but for a non-interactive
            # one we need to clear things up or the prompting for confirmation
            # in next_screen below will be confusing.
            os.system('stty sane')

    def resp_hook(self, response):
        headers = response.headers
        if 'x-updated' in headers:
            if self.server_updated is None:
                self.server_updated = headers['x-updated']
            elif self.server_updated != headers['x-updated']:
                self.restart(remove_last_screen=False)
        status = response.headers.get('x-status')
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

    def subiquity_event_noninteractive(self, event):
        if event['SUBIQUITY_EVENT_TYPE'] == 'start':
            print('start: ' + event["MESSAGE"])
        elif event['SUBIQUITY_EVENT_TYPE'] == 'finish':
            print('finish: ' + event["MESSAGE"])
            context_name = event.get('SUBIQUITY_CONTEXT_NAME', '')
            if context_name == 'subiquity/Reboot/reboot':
                self.exit()

    async def connect(self):
        print("connecting...", end='', flush=True)
        while True:
            try:
                await self.client.meta.status.GET()
            except aiohttp.ClientError:
                await asyncio.sleep(1)
                print(".", end='', flush=True)
            else:
                print()
                break

    def load_serialized_state(self):
        for controller in self.controllers.instances:
            controller.load_state()

    async def start(self):
        self.controllers.load_all()
        self.load_serialized_state()
        await self.connect()
        if self.opts.autoinstall is not None:
            await self.load_autoinstall_config()
            if not self.interactive() and not self.opts.dry_run:
                open('/run/casper-no-prompt', 'w').close()
        interactive = self.interactive()
        if interactive:
            journald_listen(
                self.aio_loop,
                [self.event_syslog_id],
                self.controllers.InstallProgress.event)
            journald_listen(
                self.aio_loop,
                [self.log_syslog_id],
                self.controllers.InstallProgress.log_line)
        else:
            journald_listen(
                self.aio_loop,
                [self.event_syslog_id],
                self.subiquity_event_noninteractive,
                seek=True)
            await asyncio.sleep(1)
        await super().start(start_urwid=interactive)
        if not interactive:
            self.select_initial_screen()

    def _exception_handler(self, loop, context):
        exc = context.get('exception')
        if self.restarting_server:
            log.debug('ignoring %s %s during restart', exc, type(exc))
            return
        if isinstance(exc, Abort):
            self.show_error_report(exc.error_report_ref)
            return
        super()._exception_handler(loop, context)

    def _remove_last_screen(self):
        last_screen = self.state_path('last-screen')
        if os.path.exists(last_screen):
            os.unlink(last_screen)

    def exit(self):
        self._remove_last_screen()
        super().exit()

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
            Error = getattr(self.controllers, "Error", None)
            if Error is not None and Error.cmds:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(Error.run())
            if self.interactive():
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

    def add_event_listener(self, listener):
        self.event_listeners.append(listener)

    def report_start_event(self, context, description):
        for listener in self.event_listeners:
            listener.report_start_event(context, description)
        self._maybe_push_to_journal('start', context, description)

    def report_finish_event(self, context, description, status):
        for listener in self.event_listeners:
            listener.report_finish_event(context, description, status)
        self._maybe_push_to_journal('finish', context, description)

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

    async def confirm_install(self):
        self.base_model.confirm()

    def interactive(self):
        if not self.autoinstall_config:
            return True
        return bool(self.autoinstall_config.get('interactive-sections'))

    def add_global_overlay(self, overlay):
        self.global_overlays.append(overlay)
        if isinstance(self.ui.body, BaseView):
            self.ui.body.show_stretchy_overlay(overlay)

    def remove_global_overlay(self, overlay):
        self.global_overlays.remove(overlay)
        if isinstance(self.ui.body, BaseView):
            self.ui.body.remove_overlay(overlay)

    def initial_controller_index(self):
        if not self.updated:
            return 0
        state_path = self.state_path('last-screen')
        if not os.path.exists(state_path):
            return 0
        with open(state_path) as fp:
            last_screen = fp.read().strip()
        controller_index = 0
        for i, controller in enumerate(self.controllers.instances):
            if controller.name == last_screen:
                controller_index = i
        return controller_index

    def select_initial_screen(self):
        self.error_reporter.load_reports()
        for report in self.error_reporter.reports:
            if report.kind == ErrorReportKind.UI and not report.seen:
                self.show_error_report(report.ref())
                break
        index = self.initial_controller_index()
        for controller in self.controllers.instances[:index]:
            controller.configured()
        self.controllers.index = index - 1
        self.next_screen()

    async def move_screen(self, increment, coro):
        try:
            await super().move_screen(increment, coro)
        except Confirm:
            if self.interactive():
                log.debug("showing InstallConfirmation over %s", self.ui.body)
                from subiquity.ui.views.installprogress import (
                    InstallConfirmation,
                    )
                self.add_global_overlay(InstallConfirmation(self))
            else:
                yes = _('yes')
                no = _('no')
                answer = no
                if 'autoinstall' in self.kernel_cmdline:
                    answer = yes
                else:
                    print(_("Confirmation is required to continue."))
                    print(_("Add 'autoinstall' to your kernel command line to"
                            " avoid this"))
                    print()
                prompt = "\n\n{} ({}|{})".format(
                    _("Continue with autoinstall?"), yes, no)
                while answer != yes:
                    print(prompt)
                    answer = input()
                self.next_screen(self.confirm_install())

    async def make_view_for_controller(self, new):
        if self.base_model.needs_confirmation(new.model_name):
            raise Confirm
        if new.interactive():
            view = await super().make_view_for_controller(new)
            if new.answers:
                self.aio_loop.call_soon(new.run_answers)
            with open(self.state_path('last-screen'), 'w') as fp:
                fp.write(new.name)
            return view
        else:
            if self.autoinstall_config and not new.autoinstall_applied:
                await new.apply_autoinstall_config()
                new.autoinstall_applied = True
            new.configured()
            raise Skip

    def show_progress(self):
        self.ui.set_body(self.controllers.InstallProgress.progress_view)

    def _network_change(self):
        self.signal.emit_signal('snapd-network-change')

    async def _proxy_set(self):
        await run_in_thread(
            self.snapd.connection.configure_proxy, self.base_model.proxy)
        self.signal.emit_signal('snapd-network-change')

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
        if key == 'ctrl g':
            from systemd import journal

            async def mock_install():
                async with self.install_lock_file.exclusive():
                    self.install_lock_file.write_content("nowhere")
                    journal.send(
                        "starting install", SYSLOG_IDENTIFIER="subiquity")
                    await asyncio.sleep(5)
            schedule_task(mock_install())
        elif key in ['ctrl e', 'ctrl r']:
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

        if report is not None and interrupt and self.interactive():
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

    def make_autoinstall(self):
        config = {'version': 1}
        for controller in self.controllers.instances:
            controller_conf = controller.make_autoinstall()
            if controller_conf:
                config[controller.autoinstall_key] = controller_conf
        return config
