# Copyright 2018 Canonical, Ltd.
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
""" Mirror View.
Select the Ubuntu archive mirror.

"""
import asyncio
import logging
from urwid import (
    connect_signal,
    LineBox,
    Padding,
    Text,
    )

from subiquitycore.ui.buttons import (
    danger_btn,
    done_btn,
    other_btn,
    )
from subiquitycore.ui.container import (
    ListBox,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.form import (
    Form,
    URLField,
)
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import TableRow, TablePile
from subiquitycore.ui.utils import button_pile, rewrap
from subiquitycore.view import BaseView

from subiquity.common.types import (
    MirrorCheckResponse,
    MirrorCheckStatus,
    )

log = logging.getLogger('subiquity.ui.views.mirror')

mirror_help = _(
    "You may provide an archive mirror that will be used instead "
    "of the default.")

MIRROR_CHECK_CONFIRMATION_TEXTS = {
    MirrorCheckStatus.RUNNING: (
        _("Mirror check still running"),
        _("""\
The check of the mirror URL is still running. You can continue but there is a
chance that the installation will fail.
"""),
        ),
    MirrorCheckStatus.FAILED: (
        _("Mirror check failed"),
        _("""\
The check of the mirror URL failed. You can continue but it is very likely that
the installation will fail.
"""),
        ),
    }


class ConfirmUncheckedMirror(Stretchy):

    def __init__(self, parent, status):
        self.parent = parent
        title, explanation = MIRROR_CHECK_CONFIRMATION_TEXTS[status]
        if status == MirrorCheckStatus.RUNNING:
            ok_btn = done_btn
        else:
            ok_btn = danger_btn
        buttons = button_pile([
            ok_btn("OK", on_press=self._ok),
            other_btn("Cancel", on_press=self._close),
            ])
        super().__init__(
            title,
            [Text(rewrap(explanation)), Text(""), buttons],
            0, 2)

    def _close(self, sender=None):
        self.parent.remove_overlay()

    def _ok(self, sender=None):
        self.parent.controller.done(
            self.parent.form.url.value)


class MirrorForm(Form):

    controller = None

    cancel_label = _("Back")

    url = URLField(_("Mirror address:"), help=mirror_help)

    def validate_url(self):
        if self.controller is not None:
            self.controller.check_url(self.url.value)


MIRROR_CHECK_STATUS_TEXTS = {
    None: _("""\
The mirror location cannot be checked because no network has been configured.
"""),
    MirrorCheckStatus.RUNNING: _("The mirror location is being tested."),
    MirrorCheckStatus.OK: _("This mirror location passed tests."),
    MirrorCheckStatus.FAILED: _("""\
This mirror location does not seem to work. The output below may help
explain the problem. You can try again once the issue has been fixed
(common problems are network issues or the system clock being wrong).
"""), }


class MirrorView(BaseView):

    title = _("Configure Ubuntu archive mirror")
    excerpt = _("If you use an alternative mirror for Ubuntu, enter its "
                "details here.")

    def __init__(self, controller, mirror):
        self.controller = controller

        self.form = MirrorForm(initial={'url': mirror})

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        self.status_text = Text("")
        self.status_spinner = Spinner()
        self.status_wrap = WidgetWrap(self.status_text)
        self.output_text = Text("")
        self.output_box = LineBox(ListBox([self.output_text]))
        self.output_wrap = WidgetWrap(self.output_box)
        self.retry_btns = button_pile([other_btn(
            _("Try again now"),
            on_press=lambda sender: self.check_url(
                self.form.url.value, True))])

        #self.update_status(check_state)

        rows = [
            ('pack', Text(_(self.excerpt))),
            ('pack', Text("")),
            ] + [('pack', r) for r in self.form.as_rows()] + [
            ('pack', Text("")),
            ('pack', self.status_wrap),
            ('pack', Text("")),
            self.output_wrap,
            ('pack', Text("")),
            ('pack', self.form.buttons),
            ('pack', Text("")),
            ]

        self.form.controller = self

        pile = Pile(rows)
        pile.focus_position = len(rows) - 2
        super().__init__(Padding(
            pile, align='center', width=("relative", 79), min_width=76))

    def check_url(self, url, retry=False):
        asyncio.create_task(self._check_url(url, retry))

    async def _check_url(self, url, retry=False):
        # TODO do something with retry?
        await self.controller.endpoint.candidate.POST(url)
        await self.controller.endpoint.check_mirror.start.POST()
        state = await self.controller.endpoint.check_mirror.progress.GET()
        self.update_status(state)

    def update_status(self, check_state: MirrorCheckResponse):
        self.status_text.set_text(rewrap(_(
            MIRROR_CHECK_STATUS_TEXTS[check_state.status])))
        self.output_text.set_text(check_state.output)

        async def cb():
            await asyncio.sleep(1)
            status = await self.controller.endpoint.check_mirror.progress.GET()
            self.update_status(status)

        if check_state.status == MirrorCheckStatus.FAILED:
            self.output_wrap._w = Pile([
                ('pack', self.retry_btns),
                ('pack', Text("")),
                self.output_box,
                ])
        elif check_state.status == MirrorCheckStatus.RUNNING:
            self.output_wrap._w = self.output_box

        if check_state.status == MirrorCheckStatus.RUNNING:
            asyncio.create_task(cb())
            self.status_spinner.start()
            self.status_wrap._w = TablePile([
                TableRow([self.status_text, self.status_spinner]),
                ])
        else:
            self.status_spinner.stop()
            self.status_wrap._w = self.status_text

        self.last_status = check_state.status

    def done(self, result):
        log.debug("User input: {}".format(result.as_data()))
        if self.last_status in [
                MirrorCheckStatus.RUNNING, MirrorCheckStatus.FAILED]:
            self.show_stretchy_overlay(
                ConfirmUncheckedMirror(self, self.last_status))
        else:
            self.controller.done(result.url.value)

    def cancel(self, result=None):
        self.controller.cancel()
