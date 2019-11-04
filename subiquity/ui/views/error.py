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
    Padding,
    Text,
    )

from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.form import (
    Toggleable,
    )
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import (
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

incomplete_text = _("""
Information is being collected from the system that will help the
developers diagnose the report.
""")


class ErrorReportStretchy(Stretchy):

    def __init__(self, app, ec, report, parent):
        self.app = app
        self.ec = ec
        self.report = report
        self.parent = parent

        self.view_btn = Toggleable(
                other_btn(
                    _("View Error Report"),
                    on_press=self.view_report))
        self.close_btn = close_btn(parent)
        btn_attrs = {'view_btn', 'close_btn'}
        w = 0
        for a in btn_attrs:
            w = max(w, widget_width(getattr(self, a)))
        for a in btn_attrs:
            b = getattr(self, a)
            setattr(self, a, Padding(b, width=w, align='center'))

        self.pile = Pile(self._pile_elements())
        self.spinner = Spinner(app.loop, style='dots')
        super().__init__("", [self.pile], 0, 0)
        connect_signal(self, 'closed', self.spinner.stop)

    def _pile_elements(self):
        widgets = [
            Text(rewrap(_(error_report_intros[self.report.kind]))),
            Text(""),
            ]

        if self.report.state == ErrorReportState.INCOMPLETE:
            self.spinner.start()
            widgets.extend([
                Text(rewrap(_(incomplete_text))),
                Text(""),
                self.spinner])
        else:
            self.spinner.stop()
            widgets.append(self.view_btn)

        widgets.extend([
            Text(""),
            self.close_btn,
            ])

        return widgets

    def view_report(self, sender):
        self.app.run_command_in_foreground(["less", self.report.path])

    def opened(self):
        self.report.mark_seen()
