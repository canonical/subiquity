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
import asyncio
from enum import auto, Enum
import logging
from typing import List, Optional

from urwid import (
    connect_signal,
    Text,
    )

from subiquitycore.ui.buttons import ok_btn
from subiquitycore.ui.form import (
    Form,
    BooleanField,
)
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.utils import screen
from subiquitycore.view import BaseView


log = logging.getLogger('subiquity.ui.views.drivers')


class DriversForm(Form):
    """ Form that shows a checkbox to configure whether we want to install the
    available drivers or not. """

    cancel_label = _("Back")

    install = BooleanField(_("Install the drivers"))


class DriversViewStatus(Enum):
    WAITING = auto()
    NO_DRIVERS = auto()
    MAIN = auto()


class DriversView(BaseView):

    title = _("Third-party drivers")

    form = None

    def __init__(self, controller, drivers: Optional[List[str]],
                 install: bool) -> None:
        self.controller = controller

        if drivers is None:
            self.make_waiting(install)
        else:
            self.make_main(install, drivers)

    def make_waiting(self, install: bool) -> None:
        """ Change the view into a spinner and start waiting for drivers
        asynchronously. """
        self.spinner = Spinner(self.controller.app.aio_loop, style='dots')
        self.spinner.start()
        rows = [
            Text(_("Looking for applicable third-party drivers...")),
            Text(""),
            self.spinner,
            ]
        self.cont_btn = ok_btn(
                _("Continue"),
                on_press=lambda sender: self.done(False))
        self._w = screen(rows, [self.cont_btn])
        asyncio.create_task(self._wait(install))
        self.status = DriversViewStatus.WAITING

    async def _wait(self, install: bool) -> None:
        """ Wait until the "list" of drivers is available and change the view
        accordingly. """
        drivers = await self.controller._wait_drivers()
        self.spinner.stop()
        if drivers:
            self.make_main(install, drivers)
        else:
            self.make_no_drivers()

    def make_no_drivers(self) -> None:
        """ Change the view into an information page that shows that no
        third-party drivers are available for installation. """

        rows = [Text(_("No applicable third-party drivers were found."))]
        self.cont_btn = ok_btn(
                _("Continue"),
                on_press=lambda sender: self.done(False))
        self._w = screen(rows, [self.cont_btn])
        self.status = DriversViewStatus.NO_DRIVERS

    def make_main(self, install: bool, drivers: List[str]) -> None:
        """ Change the view to display the drivers form. """
        self.form = DriversForm(initial={'install': install})

        excerpt = _(
            "The following third-party drivers were found. "
            "Do you want to install them?")

        def on_cancel(_: DriversForm) -> None:
            self.cancel()

        connect_signal(
            self.form, 'submit',
            lambda result: self.done(result.install.value))
        connect_signal(self.form, 'cancel', on_cancel)

        rows = [Text(f"* {driver}") for driver in drivers]
        rows.append(Text(""))
        rows.extend(self.form.as_rows())

        self._w = screen(rows, self.form.buttons, excerpt=excerpt)
        self.status = DriversViewStatus.MAIN

    def done(self, install: bool) -> None:
        log.debug("User input: %r", install)
        self.controller.done(install)

    def cancel(self) -> None:
        self.controller.cancel()
