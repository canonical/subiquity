# Copyright 2019 Canonical, Ltd.
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

from urwid import (
    connect_signal,
    disconnect_signal,
    Padding,
    ProgressBar,
    Text,
    )

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import (
    ColSpec,
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    button_pile,
    ClickableIcon,
    Color,
    disabled,
    rewrap,
    )
from subiquitycore.ui.width import (
    widget_width,
    )

from subiquity.common.errorreport import (
    ErrorReportKind,
    ErrorReportState,
    )


log = logging.getLogger('subiquity.ui.views.error')


def close_btn(stretchy, label=None):
    if label is None:
        label = _("Close")
    return other_btn(
        label,
        on_press=lambda sender: stretchy.app.remove_global_overlay(stretchy))


error_report_intros = {
    ErrorReportKind.BLOCK_PROBE_FAIL: _("""
Sorry, there was a problem examining the storage devices on this system.
"""),
    ErrorReportKind.DISK_PROBE_FAIL: _("""
Sorry, there was a problem examining the storage devices on this system.
"""),
    ErrorReportKind.INSTALL_FAIL: _("""
Sorry, there was a problem completing the installation.
"""),
    ErrorReportKind.NETWORK_FAIL: _("""
Sorry, there was a problem applying the network configuration.
"""),
    ErrorReportKind.SERVER_REQUEST_FAIL: _("""
Sorry, the installer has encountered an internal error.
"""),
    ErrorReportKind.UI: _("""
Sorry, the installer has restarted because of an error.
"""),
    ErrorReportKind.UNKNOWN: _("""
Sorry, an unknown error occurred.
"""),
}

error_report_state_descriptions = {
    ErrorReportState.INCOMPLETE: (_("""
Information is being collected from the system that will help the
developers diagnose the report.
"""), True),
    ErrorReportState.LOADING: (_("""
Loading report...
"""), True),
    ErrorReportState.ERROR_GENERATING: (_("""
Collecting information from the system failed. See the files in
/var/log/installer for more.
"""), False),
    ErrorReportState.ERROR_LOADING: (_("""
Loading the report failed. See the files in /var/log/installer for more.
"""), False),
}

error_report_options = {
    ErrorReportKind.BLOCK_PROBE_FAIL: (_("""
You can continue and the installer will just present the disks present
in the system and not other block devices, or you may be able to fix
the issue by switching to a shell and reconfiguring the system's block
devices manually.
"""), ['debug_shell', 'continue']),
    ErrorReportKind.DISK_PROBE_FAIL: (_("""
You may be able to fix the issue by switching to a shell and
reconfiguring the system's block devices manually.
"""), ['debug_shell', 'continue']),
    ErrorReportKind.NETWORK_FAIL: (_("""
You can continue with the installation but it will be assumed the network
is not functional.
"""), ['continue']),
    ErrorReportKind.SERVER_REQUEST_FAIL: (_("""
You can continue or restart the installer.
"""), ['continue', 'restart']),
    ErrorReportKind.INSTALL_FAIL: (_("""
Do you want to try starting the installation again?
"""), ['restart', 'close']),
    ErrorReportKind.UI: (
        _("Select continue to try the installation again."), ['continue']),
    ErrorReportKind.UNKNOWN: ("", ['close']),
}


submit_text = _("""
If you want to help improve the installer, you can send an error report.
""")


class ErrorReportStretchy(Stretchy):

    def __init__(self, app, ref, interrupting=True):
        self.app = app
        self.error_ref = ref
        self.report = app.error_reporter.get(ref)
        self.pending = None
        if self.report is None:
            self.app.aio_loop.create_task(self._wait())
        else:
            connect_signal(self.report, 'changed', self._report_changed)
            self.report.mark_seen()
        self.interrupting = interrupting
        self.min_wait = self.app.aio_loop.create_task(asyncio.sleep(0.1))

        self.btns = {
            'cancel': other_btn(
                _("Cancel upload"), on_press=self.cancel_upload),
            'close': close_btn(self, _("Close report")),
            'continue': close_btn(self, _("Continue")),
            'debug_shell': other_btn(
                _("Switch to a shell"), on_press=self.debug_shell),
            'restart': other_btn(
                _("Restart the installer"), on_press=self.restart),
            'submit': other_btn(
                _("Send to Canonical"), on_press=self.submit),
            'submitted': disabled(other_btn(_("Sent to Canonical"))),
            'view': other_btn(
                _("View full report"), on_press=self.view_report),
            }
        w = 0
        for n, b in self.btns.items():
            w = max(w, widget_width(b))
        for n, b in self.btns.items():
            self.btns[n] = Padding(b, width=w, align='center')

        self.spinner = Spinner(app.aio_loop, style='dots')
        self.pile = Pile([])
        self.pile.contents[:] = [
            (w, self.pile.options('pack')) for w in self._pile_elements()]
        super().__init__("", [self.pile], 0, 0)
        connect_signal(self, 'closed', self.spinner.stop)

    async def _wait(self):
        self.report = await self.app.error_reporter.get_wait(
            self.error_ref)
        self.error_ref = self.report.ref()
        connect_signal(self.report, 'changed', self._report_changed)
        self.report.mark_seen()
        await self._report_changed_()

    def pb(self, upload):
        pb = ProgressBar(
            normal='progress_incomplete',
            complete='progress_complete',
            current=upload.bytes_sent,
            done=upload.bytes_to_send)

        def _progress():
            pb.done = upload.bytes_to_send
            pb.current = upload.bytes_sent
        connect_signal(upload, 'progress', _progress)

        return pb

    def _pile_elements(self):
        btns = self.btns.copy()

        widgets = [
            Text(rewrap(_(error_report_intros[self.error_ref.kind]))),
            Text(""),
            ]

        self.spinner.stop()

        if self.error_ref.state == ErrorReportState.DONE:
            assert self.report
            widgets.append(btns['view'])
            widgets.append(Text(""))
            widgets.append(Text(rewrap(_(submit_text))))
            widgets.append(Text(""))

            if self.report.uploader:
                if self.upload_pb is None:
                    self.upload_pb = self.pb(self.report.uploader)
                widgets.append(self.upload_pb)
            else:
                if self.report.oops_id:
                    widgets.append(btns['submitted'])
                else:
                    widgets.append(btns['submit'])
                self.upload_pb = None

            fs_label, fs_loc = self.report.persistent_details
            if fs_label is not None:
                location_text = _(
                    "The error report has been saved to\n\n  {loc}\n\non the "
                    "filesystem with label {label!r}.").format(
                        loc=fs_loc, label=fs_label)
                widgets.extend([
                    Text(""),
                    Text(location_text),
                    ])
        else:
            text, spin = error_report_state_descriptions[self.error_ref.state]
            widgets.append(Text(rewrap(_(text))))
            if spin:
                self.spinner.start()
                widgets.extend([
                    Text(""),
                    self.spinner])

        if self.report and self.report.uploader:
            widgets.extend([Text(""), btns['cancel']])
        elif self.interrupting:
            if self.error_ref.state != ErrorReportState.INCOMPLETE:
                text, btn_names = error_report_options[self.error_ref.kind]
                if text:
                    widgets.extend([Text(""), Text(rewrap(_(text)))])
                for b in btn_names:
                    widgets.extend([Text(""), btns[b]])
        else:
            widgets.extend([
                Text(""),
                btns['close'],
                ])

        return widgets

    def _report_changed(self):
        if self.pending:
            self.pending.cancel()
        self.pending = self.app.aio_loop.create_task(asyncio.sleep(0.1))
        self.change_task = self.app.aio_loop.create_task(
            self._report_changed_())

    async def _report_changed_(self):
        await self.pending
        self.pending = None
        await self.min_wait
        self.min_wait = self.app.aio_loop.create_task(asyncio.sleep(1))
        if self.report:
            self.error_ref = self.report.ref()
        self.pile.contents[:] = [
            (w, self.pile.options('pack')) for w in self._pile_elements()]
        if self.pile.selectable():
            while not self.pile.focus.selectable():
                self.pile.focus_position += 1

    def debug_shell(self, sender):
        self.app.debug_shell()

    def restart(self, sender):
        self.app.restart(restart_server=True)

    def view_report(self, sender):
        self.app.run_command_in_foreground(["less", self.report.path])

    def submit(self, sender):
        self.report.upload()

    def cancel_upload(self, sender):
        self.report.uploader.cancelled = True
        self.report.uploader = None
        self._report_changed()

    def closed(self):
        if self.report:
            disconnect_signal(self.report, 'changed', self._report_changed)


class ErrorReportListStretchy(Stretchy):

    def __init__(self, app):
        self.app = app
        rows = [
            TableRow([
                Text(""),
                Text(_("DATE")),
                Text(_("KIND")),
                Text(_("STATUS")),
                Text(""),
            ])]
        self.report_to_row = {}
        self.app.error_reporter.load_reports()
        for report in self.app.error_reporter.reports:
            connect_signal(report, "changed", self._report_changed, report)
            r = self.report_to_row[report] = self.row_for_report(report)
            rows.append(r)
        self.table = TablePile(rows, colspecs={1: ColSpec(can_shrink=True)})
        widgets = [
            Text(_("Select an error report to view:")),
            Text(""),
            self.table,
            Text(""),
            button_pile([close_btn(self)]),
            ]
        super().__init__("", widgets, 2, 2)

    def open_report(self, sender, report):
        self.app.add_global_overlay(
            ErrorReportStretchy(self.app, report, False))

    def state_for_report(self, report):
        if report.seen:
            return _("VIEWED")
        return _("UNVIEWED")

    def cells_for_report(self, report):
        date = report.pr.get("Date", "???")
        icon = ClickableIcon(date)
        connect_signal(icon, 'click', self.open_report, report)
        return [
            Text("["),
            icon,
            Text(_(report.kind.value)),
            Text(_(self.state_for_report(report))),
            Text("]"),
            ]

    def row_for_report(self, report):
        return Color.menu_button(
            TableRow(self.cells_for_report(report)))

    def _report_changed(self, report):
        old_r = self.report_to_row.get(report)
        if old_r is None:
            return
        old_r = old_r.base_widget
        new_cells = self.cells_for_report(report)
        for (s1, old_c), new_c in zip(old_r.cells, new_cells):
            old_c.set_text(new_c.text)
        self.table.invalidate()
