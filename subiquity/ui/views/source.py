# Copyright 2021 Canonical, Ltd.
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
from typing import List

from urwid import Text, connect_signal

from subiquitycore.ui.container import ListBox
from subiquitycore.ui.form import BooleanField, Form, RadioButtonField
from subiquitycore.ui.utils import screen
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.source")


class SourceView(BaseView):
    title = _("Choose type of install")

    def __init__(self, controller, sources, current_id, search_drivers: bool):
        self.controller = controller

        group: List[RadioButtonField] = []

        ns = {
            "cancel_label": _("Back"),
        }
        initial = {}

        for default in True, False:
            for source in sorted(sources, key=lambda s: s.id):
                if source.default != default:
                    continue
                ns[source.id] = RadioButtonField(
                    group, source.name, "\n" + source.description
                )
                initial[source.id] = source.id == current_id

        ns["search_drivers"] = BooleanField(
            _("Search for third-party drivers"),
            "\n"
            + _(
                "This software is subject to license terms included with its "
                "documentation. Some is proprietary."
            )
            + " "
            + _(
                "Third-party drivers should not be installed on systems that "
                "will be used for FIPS or the real-time kernel."
            ),
        )
        initial["search_drivers"] = search_drivers

        SourceForm = type(Form)("SourceForm", (Form,), ns)
        log.debug("%r %r", ns, current_id)

        self.form = SourceForm(initial=initial)

        connect_signal(self.form, "submit", self.done)
        connect_signal(self.form, "cancel", self.cancel)

        excerpt = _("Choose the base for the installation.")

        # NOTE Hack to insert the "Additional options" text between two fields
        # of the form.
        rows = self.form.as_rows()
        rows.insert(-2, Text(""))
        rows.insert(-2, Text("Additional options"))

        super().__init__(
            screen(
                ListBox(rows), self.form.buttons, excerpt=excerpt, focus_buttons=True
            )
        )

    def done(self, result):
        log.debug("User input: %s", result.as_data())
        search_drivers = result.as_data()["search_drivers"]
        for k, v in result.as_data().items():
            if k == "search_drivers":
                continue
            if v:
                self.controller.done(k, search_drivers=search_drivers)

    def cancel(self, result=None):
        self.controller.cancel()
