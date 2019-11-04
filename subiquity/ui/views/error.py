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

import logging

from urwid import (
    connect_signal,
    disconnect_signal,
    Padding,
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
    rewrap,
    )
from subiquitycore.ui.width import (
    widget_width,
    )

from subiquity.controllers.error import (
    ErrorReportKind,
    ErrorReportState,
    )


log = logging.getLogger('subiquity.ui.error')


def close_btn(parent, label=None):
    if label is None:
        label = _("Close")
    return other_btn(label, on_press=lambda sender: parent.remove_overlay())


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


class ErrorReportStretchy(Stretchy):

    def __init__(self, app, ec, report, parent):
        self.app = app
        self.ec = ec
        self.report = report
        self.parent = parent

        self.view_btn = other_btn(
            _("View Error Report"),
            on_press=self.view_report)
        self.close_btn = close_btn(parent)
        btn_attrs = {'view_btn', 'close_btn'}
        w = 0
        for a in btn_attrs:
            w = max(w, widget_width(getattr(self, a)))
        for a in btn_attrs:
            b = getattr(self, a)
            setattr(self, a, Padding(b, width=w, align='center'))

        self.spinner = Spinner(app.loop, style='dots')
        self.pile = Pile([])
        self._report_changed()
        super().__init__("", [self.pile], 0, 0)
        connect_signal(self, 'closed', self.spinner.stop)

    def _pile_elements(self):
        widgets = [
            Text(rewrap(_(error_report_intros[self.report.kind]))),
            Text(""),
            ]

        self.spinner.stop()

        if self.report.state == ErrorReportState.DONE:
            widgets.append(self.view_btn)
        else:
            text, spin = error_report_state_descriptions[self.report.state]
            widgets.append(Text(rewrap(_(text))))
            if spin:
                self.spinner.start()
                widgets.extend([
                    Text(""),
                    self.spinner])

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

        widgets.extend([
            Text(""),
            self.close_btn,
            ])

        return widgets

    def _report_changed(self):
        self.pile.contents[:] = [
            (w, self.pile.options('pack')) for w in self._pile_elements()]
        while not self.pile.focus.selectable():
            self.pile.focus_position += 1

    def view_report(self, sender):
        self.app.run_command_in_foreground(["less", self.report.path])

    def opened(self):
        self.report.mark_seen()
        connect_signal(self.report, 'changed', self._report_changed)

    def closed(self):
        disconnect_signal(self.report, 'changed', self._report_changed)


class ErrorReportListStretchy(Stretchy):

    def __init__(self, app, parent):
        self.app = app
        self.parent = parent
        self.ec = app.error_controller
        rows = [
            TableRow([
                Text(""),
                Text(_("DATE")),
                Text(_("KIND")),
                Text(_("STATUS")),
                Text(""),
            ])]
        for report in self.ec.reports:
            rows.append(self.row_for_report(report))
        self.table = TablePile(rows, colspecs={1: ColSpec(can_shrink=True)})
        widgets = [
            Text(_("Select an error report to view:")),
            Text(""),
            self.table,
            Text(""),
            button_pile([close_btn(parent)]),
            ]
        super().__init__("", widgets, 2, 2)

    def open_report(self, sender, report):
        self.app.show_error_report(report)

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
