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
import platform
import sys
import traceback

import apport.hookutils

from subiquitycore.core import Application

from subiquity.controllers.error import (
    ErrorController,
    ErrorReportKind,
    )
from subiquity.models.subiquity import SubiquityModel
from subiquity.snapd import (
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
        self.snapd_connection = connection
        self.signal.connect_signals([
            ('network-proxy-set', self._proxy_set),
            ('network-change', self._network_change),
            ])
        self._apport_data = []
        self._apport_files = []

    def run(self):
        try:
            super().run()
        except Exception:
            print("generating crash report")
            report = self.make_apport_report(
                ErrorReportKind.UI, "Installer UI", interrupt=False, wait=True)
            print("report saved to {}".format(report.path))
            raise

    def select_initial_screen(self, index):
        super().select_initial_screen(index)
        for report in self.error_controller.reports:
            if report.kind == ErrorReportKind.UI and not report.seen:
                log.debug("showing new error %r", report.base)
                self.show_error_report(report)
                return

    def _network_change(self):
        self.signal.emit_signal('snapd-network-change')

    def _proxy_set(self):
        self.run_in_bg(
            lambda: self.snapd_connection.configure_proxy(
                self.base_model.proxy),
            lambda fut: (
                fut.result(), self.signal.emit_signal('snapd-network-change')),
            )

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
            "bash", before_hook=_before, cwd='/')

    def load_controllers(self):
        super().load_controllers()
        self.error_controller = ErrorController(self)

    def start_controllers(self):
        super().start_controllers()
        self.error_controller.start()

    def note_file_for_apport(self, key, path):
        self._apport_files.append((key, path))

    def note_data_for_apport(self, key, value):
        self._apport_data.append((key, value))

    def schedule_task(self, coro):
        loop = asyncio.get_event_loop()
        loop.call_soon(asyncio.create_task, coro)

    async def run_in_thread(self, func, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)

    def make_apport_report(self, kind, thing, *, interrupt, wait=False, **kw):
        log.debug("generating crash report")

        try:
            report = self.error_controller.create_report(kind)
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
