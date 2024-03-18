# Copyright 2017 Canonical, Ltd.
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

from urwid import Text

styles = {
    "dots": {
        "texts": [
            t.replace("*", "\N{bullet}")
            for t in [
                "|*----|",
                "|-*---|",
                "|--*--|",
                "|---*-|",
                "|----*|",
                "|---*-|",
                "|--*--|",
                "|-*---|",
            ]
        ],
        "rate": 0.2,
    },
    "spin": {
        "texts": ["-", "\\", "|", "/"],
        "rate": 0.1,
    },
}


log = logging.getLogger("subiquitycore.ui.spinner")


class Spinner(Text):
    """An animation used when loading elements.
    Use the .start() method to start the animation. You must ensure that you
    call .stop() otherwise the Spinner will continue firing events until the
    event loop is closed (even if the spinner is no longer visible on the
    screen)."""

    def __init__(self, style="spin", align="center", *, debug=False, app=None):
        self.debug = debug
        self.spin_index = 0
        self.spin_text = styles[style]["texts"]
        self.rate = styles[style]["rate"]
        self.app = app
        super().__init__("", align=align)
        self._spin_task = None

    def spin(self):
        if self.debug:
            log.debug("spinning spinner %s", id(self))
        self.spin_index = (self.spin_index + 1) % len(self.spin_text)
        self.set_text(self.spin_text[self.spin_index])
        if self.app is not None:
            self.app.request_screen_redraw()

    async def _spin(self):
        while True:
            self.spin()
            await asyncio.sleep(self.rate)

    def start(self):
        if self._spin_task is not None:
            return
        if self.debug:
            log.debug("starting spinner %s", id(self))
        self.stop()
        self._spin_task = asyncio.create_task(self._spin())

    def stop(self):
        if self.debug:
            log.debug("stopping spinner %s", id(self))
        self.set_text("")
        if self._spin_task is not None:
            self._spin_task.cancel()
            self._spin_task = None
