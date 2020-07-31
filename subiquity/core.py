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

import logging
import os
import platform
import shlex
import signal
import sys
import traceback
import time
import urwid

import jsonschema

import yaml

from subiquitycore.async_helpers import (
    run_in_thread,
    schedule_task,
    )
from subiquitycore.tuicontroller import Skip
from subiquitycore.tui import TuiApplication
from subiquitycore.snapd import (
    AsyncSnapd,
    FakeSnapdConnection,
    SnapdConnection,
    )
from subiquitycore.view import BaseView

from subiquity.common.errorreport import (
    ErrorReporter,
    ErrorReportKind,
    )
from subiquity.journald import journald_listener
from subiquity.lockfile import Lockfile
from subiquity.models.subiquity import SubiquityModel
from subiquity.ui.frame import SubiquityUI
from subiquity.ui.views.error import ErrorReportStretchy
from subiquity.ui.views.help import HelpMenu


log = logging.getLogger('subiquity.core')


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
        if not opts.bootloader == 'none' and platform.machine() != 's390x':
            self.controllers.remove("Zdev")

        self.journal_fd, self.journal_watcher = journald_listener(
            ["subiquity"], self.subiquity_event, seek=True)
        self.help_menu = HelpMenu(self)
        super().__init__(opts)
        self.event_listeners = []
        self.install_lock_file = Lockfile(self.state_path("installing"))
        self.global_overlays = []
        self.block_log_dir = block_log_dir
        self.kernel_cmdline = shlex.split(opts.kernel_cmdline)
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

        self.autoinstall_config = {}
        self.report_to_show = None
        self.show_progress_handle = None
        self.progress_shown_time = self.aio_loop.time()
        self.progress_showing = False
        self.error_reporter = ErrorReporter(
            self.context.child("ErrorReporter"), self.opts.dry_run, self.root)

        self.note_data_for_apport("SnapUpdated", str(self.updated))
        self.note_data_for_apport("UsingAnswers", str(bool(self.answers)))

        self.install_confirmed = False

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

    def restart(self, remove_last_screen=True):
        if remove_last_screen:
            self._remove_last_screen()
        self.urwid_loop.screen.stop()
        cmdline = ['snap', 'run', 'subiquity']
        if self.opts.dry_run:
            cmdline = [
                sys.executable, '-m', 'subiquity.cmd.tui',
                ] + sys.argv[1:]
        os.execvp(cmdline[0], cmdline)

    def make_screen(self, input=None, output=None):
        if self.interactive():
            return super().make_screen(input, output)
        else:
            r, w = os.pipe()
            s = urwid.raw_display.Screen(
                input=os.fdopen(r), output=open('/dev/null', 'w'))
            s.get_cols_rows = lambda: (80, 24)
            return s

    def get_primary_tty(self):
        tty = '/dev/tty1'
        for work in self.kernel_cmdline:
            if work.startswith('console='):
                tty = '/dev/' + work[len('console='):].split(',')[0]
        return tty

    def load_autoinstall_config(self):
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
        self.controllers.load("Reporting")
        self.controllers.Reporting.start()
        self.controllers.load("Error")
        with self.context.child("core_validation", level="INFO"):
            jsonschema.validate(self.autoinstall_config, self.base_schema)
        self.controllers.load("Early")
        if self.controllers.Early.cmds:
            stamp_file = self.state_path("early-commands")
            if our_tty != primary_tty:
                print(
                    _("waiting for installer running on {tty} to run early "
                      "commands").format(tty=primary_tty))
                while not os.path.exists(stamp_file):
                    time.sleep(1)
            elif not os.path.exists(stamp_file):
                self.aio_loop.run_until_complete(
                    self.controllers.Early.run())
                self.new_event_loop()
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

    def new_event_loop(self):
        super().new_event_loop()
        self.aio_loop.add_reader(self.journal_fd, self.journal_watcher)

    def run(self):
        try:
            if self.opts.autoinstall is not None:
                self.load_autoinstall_config()
                if not self.interactive() and not self.opts.dry_run:
                    open('/run/casper-no-prompt', 'w').close()
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
                self.new_event_loop()
                self.aio_loop.run_until_complete(Error.run())
            if self.interactive():
                self._remove_last_screen()
                raise
            else:
                traceback.print_exc()
                signal.pause()

    def add_event_listener(self, listener):
        self.event_listeners.append(listener)

    def report_start_event(self, context, description):
        for listener in self.event_listeners:
            listener.report_start_event(context, description)

    def report_finish_event(self, context, description, status):
        for listener in self.event_listeners:
            listener.report_finish_event(context, description, status)

    def confirm_install(self):
        self.install_confirmed = True
        self.controllers.InstallProgress.confirmation.set()

    def _cancel_show_progress(self):
        if self.show_progress_handle is not None:
            self.ui.block_input = False
            self.show_progress_handle.cancel()
            self.show_progress_handle = None

    def next_screen(self):
        can_install = all(e.is_set() for e in self.base_model.install_events)
        if can_install and not self.install_confirmed:
            if self.interactive():
                log.debug("showing InstallConfirmation over %s", self.ui.body)
                from subiquity.ui.views.installprogress import (
                    InstallConfirmation,
                    )
                self._cancel_show_progress()
                self.add_global_overlay(
                    InstallConfirmation(self.ui.body, self))
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
                self.confirm_install()
                super().next_screen()
        else:
            super().next_screen()

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

    def select_initial_screen(self, index):
        self.error_reporter.start_loading_reports()
        for report in self.error_reporter.reports:
            if report.kind == ErrorReportKind.UI and not report.seen:
                self.show_error_report(report)
                break
        super().select_initial_screen(index)

    def select_screen(self, new):
        if new.interactive():
            self._cancel_show_progress()
            if self.progress_showing:
                shown_for = self.aio_loop.time() - self.progress_shown_time
                remaining = 1.0 - shown_for
                if remaining > 0.0:
                    self.aio_loop.call_later(
                        remaining, self.select_screen, new)
                    return
            self.progress_showing = False
            super().select_screen(new)
        elif self.autoinstall_config and not new.autoinstall_applied:
            if self.interactive() and self.show_progress_handle is None:
                self.ui.block_input = True
                self.show_progress_handle = self.aio_loop.call_later(
                    0.1, self._show_progress)
            schedule_task(self._apply(new))
        else:
            new.configured()
            raise Skip

    def _show_progress(self):
        self.ui.block_input = False
        self.progress_shown_time = self.aio_loop.time()
        self.progress_showing = True
        self.ui.set_body(self.controllers.InstallProgress.progress_view)

    async def _apply(self, controller):
        await controller.apply_autoinstall_config()
        controller.autoinstall_applied = True
        controller.configured()
        self.next_screen()

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
            import asyncio
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
            self.show_error_report(report)

        return report

    def show_error_report(self, report):
        log.debug("show_error_report %r", report.base)
        if isinstance(self.ui.body, BaseView):
            w = getattr(self.ui.body._w, 'stretchy', None)
            if isinstance(w, ErrorReportStretchy):
                # Don't show an error if already looking at one.
                return
        self.add_global_overlay(ErrorReportStretchy(self, report))

    def make_autoinstall(self):
        config = {'version': 1}
        for controller in self.controllers.instances:
            controller_conf = controller.make_autoinstall()
            if controller_conf:
                config[controller.autoinstall_key] = controller_conf
        return config
