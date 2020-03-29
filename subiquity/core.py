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
import signal
import sys
import traceback
import urwid

import apport.hookutils

import jsonschema

import yaml

from subiquitycore.async_helpers import (
    run_in_thread,
    schedule_task,
    )
from subiquitycore.controller import Skip
from subiquitycore.core import Application
from subiquitycore.utils import run_command

from subiquity.controllers.error import (
    ErrorReportKind,
    )
from subiquity.models.subiquity import SubiquityModel
from subiquity.snapd import (
    AsyncSnapd,
    FakeSnapdConnection,
    SnapdConnection,
    )
from subiquity.ui.frame import SubiquityUI
from subiquity.ui.views.error import ErrorReportStretchy


log = logging.getLogger('subiquity.core')


DEBUG_SHELL_INTRO = _("""\
Installer shell session activated.

This shell session is running inside the installer environment.  You
will be returned to the installer when this shell is exited, for
example by typing Control-D or 'exit'.

Be aware that this is an ephemeral environment.  Changes to this
environment will not survive a reboot. If the install has started, the
installed system will be mounted at /target.""")


class Subiquity(Application):

    snapd_socket_path = '/run/snapd.socket'

    base_schema = {
        'type': 'object',
        'properties': {
            'version': {
                'type': 'integer',
                'minumum': 1,
                'maximum': 1,
                },
            },
        'required': ['version'],
        'additionalProperties': True,
        }

    from subiquity.palette import COLORS, STYLES, STYLES_MONO

    project = "subiquity"

    def make_model(self):
        root = '/'
        if self.opts.dry_run:
            root = os.path.abspath('.subiquity')
        return SubiquityModel(root, self.opts.sources)

    def make_ui(self):
        return SubiquityUI(self)

    controllers = [
        "Early",
        "Reporting",
        "Error",
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
    ]

    def __init__(self, opts, block_log_dir):
        if not opts.bootloader == 'none' and platform.machine() != 's390x':
            self.controllers.remove("Zdev")

        super().__init__(opts)
        self.block_log_dir = block_log_dir
        if opts.snaps_from_examples:
            connection = FakeSnapdConnection(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(__file__)),
                    "examples", "snaps"))
        else:
            connection = SnapdConnection(self.root, self.snapd_socket_path)
        self.snapd = AsyncSnapd(connection)
        self.signal.connect_signals([
            ('network-proxy-set', lambda: schedule_task(self._proxy_set())),
            ('network-change', self._network_change),
            ])
        self._apport_data = []
        self._apport_files = []

        self.autoinstall_config = {}
        self.note_data_for_apport("SnapUpdated", str(self.updated))
        self.note_data_for_apport("UsingAnswers", str(bool(self.answers)))

        self.reboot_on_exit = False

    def exit(self):
        if self.reboot_on_exit and not self.opts.dry_run:
            run_command(["/sbin/reboot"])
        else:
            super().exit()

    def restart(self, remove_last_screen=True):
        if remove_last_screen:
            self._remove_last_screen()
        self.urwid_loop.screen.stop()
        cmdline = ['snap', 'run', 'subiquity']
        if self.opts.dry_run:
            cmdline = [sys.executable] + sys.argv
        os.execvp(cmdline[0], cmdline)

    def make_screen(self):
        if self.interactive():
            return super().make_screen()
        else:
            r, w = os.pipe()
            s = urwid.raw_display.Screen(
                input=os.fdopen(r), output=open('/dev/null', 'w'))
            s.get_cols_rows = lambda: (80, 24)
            return s

    def load_autoinstall_config(self):
        with open(self.opts.autoinstall) as fp:
            self.autoinstall_config = yaml.safe_load(fp)
        self.controllers.load("Reporting")
        self.controllers.Reporting.start()
        self.controllers.load("Error")
        with self.context.child("core_validation", level="INFO"):
            jsonschema.validate(self.autoinstall_config, self.base_schema)
        self.controllers.load("Early")
        if self.controllers.Early.cmds:
            self.aio_loop.run_until_complete(
                self.controllers.Early.run())
            self.new_event_loop()
            with open(self.opts.autoinstall) as fp:
                self.autoinstall_config = yaml.safe_load(fp)
            with self.context.child("core_validation", level="INFO"):
                jsonschema.validate(self.autoinstall_config, self.base_schema)
            for controller in self.controllers.instances:
                controller.setup_autoinstall()

    def run(self):
        try:
            if self.opts.autoinstall is not None:
                self.load_autoinstall_config()
            super().run()
            if self.controllers.Late.cmds:
                self.new_event_loop()
                self.aio_loop.run_until_complete(self.controllers.Late.run())
        except Exception:
            print("generating crash report")
            try:
                report = self.make_apport_report(
                    ErrorReportKind.UI, "Installer UI", interrupt=False, wait=True)
                print("report saved to {}".format(report.path))
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

    def report_start_event(self, name, description, level="INFO"):
        # report_start_event gets called when the Reporting controller
        # is being loaded...
        Reporting = getattr(self.controllers, "Reporting", None)
        if Reporting is not None:
            Reporting.report_start_event(name, description, level)

    def report_finish_event(self, name, description, status, level="INFO"):
        Reporting = getattr(self.controllers, "Reporting", None)
        if Reporting is not None:
            Reporting.report_finish_event(name, description, status, level)

    def interactive(self):
        if not self.autoinstall_config:
            return True
        return bool(self.autoinstall_config.get('interactive-sections'))

    def select_initial_screen(self, index):
        super().select_initial_screen(index)
        for report in self.controllers.Error.reports:
            if report.kind == ErrorReportKind.UI and not report.seen:
                log.debug("showing new error %r", report.base)
                self.show_error_report(report)
                return

    def select_screen(self, new):
        if new.interactive():
            super().select_screen(new)
        elif self.autoinstall_config and not new.autoinstall_applied:
            schedule_task(self._apply(new))
        else:
            raise Skip

    async def _apply(self, controller):
        with controller.context.child("apply_autoinstall_config"):
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
            if not self.ui.right_icon.showing_something:
                self.ui.right_icon.open_pop_up()
        elif self.opts.dry_run and key in ['ctrl e', 'ctrl r']:
            interrupt = key == 'ctrl e'
            try:
                1/0
            except ZeroDivisionError:
                self.make_apport_report(
                    ErrorReportKind.UNKNOWN, "example", interrupt=interrupt)
        elif self.opts.dry_run and key == 'ctrl u':
            1/0
        elif key in ['ctrl z', 'f2']:
            self.debug_shell()
        else:
            super().unhandled_input(key)

    def debug_shell(self):

        def _before():
            os.system("clear")
            print(DEBUG_SHELL_INTRO)

        self.run_command_in_foreground(
            ["bash"], before_hook=_before, cwd='/')

    def note_file_for_apport(self, key, path):
        self._apport_files.append((key, path))

    def note_data_for_apport(self, key, value):
        self._apport_data.append((key, value))

    def make_apport_report(self, kind, thing, *, interrupt, wait=False, **kw):
        log.debug("generating crash report")

        try:
            report = self.controllers.Error.create_report(kind)
        except Exception:
            log.exception("creating crash report failed")
            return

        etype = sys.exc_info()[0]
        if etype is not None:
            report.pr["Title"] = "{} crashed with {}".format(
                thing, etype.__name__)
            report.pr['Traceback'] = traceback.format_exc()
        else:
            report.pr["Title"] = thing

        log.info(
            "saving crash report %r to %s", report.pr["Title"], report.path)

        apport_files = self._apport_files[:]
        apport_data = self._apport_data.copy()

        def _bg_attach_hook():
            # Attach any stuff other parts of the code think we should know
            # about.
            for key, path in apport_files:
                apport.hookutils.attach_file_if_exists(report.pr, path, key)
            for key, value in apport_data:
                report.pr[key] = value
            for key, value in kw.items():
                report.pr[key] = value

        report.add_info(_bg_attach_hook, wait)

        if interrupt:
            self.show_error_report(report)

        # In the fullness of time we should do the signature thing here.
        return report

    def show_error_report(self, report):
        log.debug("show_error_report %r", report.base)
        w = getattr(self.ui.body._w, 'top_w', None)
        if isinstance(w, ErrorReportStretchy):
            # Don't show an error if already looking at one.
            return
        self.ui.body.show_stretchy_overlay(
            ErrorReportStretchy(self, self.ui.body, report))

    def make_autoinstall(self):
        config = {}
        for controller in self.controllers.instances:
            controller_conf = controller.make_autoinstall()
            if controller_conf:
                config[controller.autoinstall_key] = controller_conf
        return config
