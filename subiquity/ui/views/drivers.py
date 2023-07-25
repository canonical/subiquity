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

""" Module defining the view for third-party drivers installation.

"""
import logging
from enum import Enum, auto
from typing import List, Optional

from urwid import Text, connect_signal

from subiquitycore.async_helpers import run_bg_task
from subiquitycore.ui.buttons import back_btn, ok_btn
from subiquitycore.ui.form import Form, RadioButtonField
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.utils import screen
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.drivers")


class DriversForm(Form):
    """Form that shows a checkbox to configure whether we want to install the
    available drivers or not."""

    cancel_label = _("Back")
    ok_label = _("Continue")

    group: List[RadioButtonField] = []

    install = RadioButtonField(group, _("Install all third-party drivers"))
    do_not_install = RadioButtonField(
        group, _("Do not install third-party drivers now")
    )


class DriversViewStatus(Enum):
    WAITING = auto()
    NO_DRIVERS = auto()
    MAIN = auto()


class DriversView(BaseView):
    title = _("Third-party drivers")

    form = None

    def __init__(
        self, controller, drivers: Optional[List[str]], install: bool, local_only: bool
    ) -> None:
        self.controller = controller
        self.local_only = local_only

        self.search_later = [
            Text(
                _(
                    "Note: Once the installation has finished and you are "
                    + "connected to a network, you can search again for "
                    + "third-party drivers using the following command:"
                )
            ),
            Text(""),
            Text("  $ ubuntu-drivers list --recommended --gpgpu"),
        ]

        if drivers is None:
            self.make_waiting(install)
        elif not drivers:
            self.make_no_drivers()
        else:
            self.make_main(install, drivers)

    def make_waiting(self, install: bool) -> None:
        """Change the view into a spinner and start waiting for drivers
        asynchronously."""
        self.spinner = Spinner(style="dots")
        self.spinner.start()

        if self.local_only:
            looking_for_drivers = _(
                "Not connected to a network. "
                + "Looking for applicable third-party "
                + "drivers available locally..."
            )
        else:
            looking_for_drivers = _(
                "Looking for applicable third-party "
                + "drivers available locally or online..."
            )

        rows = [
            Text(looking_for_drivers),
            Text(""),
            self.spinner,
        ]
        self.back_btn = back_btn(_("Back"), on_press=lambda sender: self.cancel())
        self._w = screen(rows, [self.back_btn])
        run_bg_task(self._wait(install))
        self.status = DriversViewStatus.WAITING

    async def _wait(self, install: bool) -> None:
        """Wait until the "list" of drivers is available and change the view
        accordingly."""
        drivers = await self.controller._wait_drivers()
        self.spinner.stop()
        if drivers:
            self.make_main(install, drivers)
        else:
            self.make_no_drivers()

    def make_no_drivers(self) -> None:
        """Change the view into an information page that shows that no
        third-party drivers are available for installation."""

        if self.local_only:
            no_drivers_found = _(
                "No applicable third-party drivers are " + "available locally."
            )
        else:
            no_drivers_found = _(
                "No applicable third-party drivers are "
                + "available locally or online."
            )

        rows = [Text(no_drivers_found)]
        if self.local_only:
            rows.append(Text(""))
            rows.extend(self.search_later)

        self.cont_btn = ok_btn(_("Continue"), on_press=lambda sender: self.done(False))
        self.back_btn = back_btn(_("Back"), on_press=lambda sender: self.cancel())
        self._w = screen(rows, [self.cont_btn, self.back_btn])
        self.status = DriversViewStatus.NO_DRIVERS

    def make_main(self, install: bool, drivers: List[str]) -> None:
        """Change the view to display the drivers form."""
        self.form = DriversForm(
            initial={
                "install": bool(install),
                "do_not_install": (not install),
            }
        )

        excerpt = _(
            "The following third-party drivers were found. Do you want to install them?"
        )

        def on_cancel(_: DriversForm) -> None:
            self.cancel()

        connect_signal(
            self.form, "submit", lambda result: self.done(result.install.value)
        )
        connect_signal(self.form, "cancel", on_cancel)

        rows = [Text(f"* {driver}") for driver in drivers]
        rows.append(Text(""))
        rows.extend(self.form.as_rows())

        if self.local_only:
            rows.append(Text(""))
            rows.extend(self.search_later)

        self._w = screen(rows, self.form.buttons, excerpt=excerpt)
        self.status = DriversViewStatus.MAIN

    def done(self, install: bool) -> None:
        log.debug("User input: %r", install)
        self.controller.done(install)

    def cancel(self) -> None:
        self.controller.cancel()
