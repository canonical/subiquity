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
import json
import logging

import aiohttp

from urwid import (
    ProgressBar,
    Text,
    WidgetWrap,
    )

from subiquitycore.async_helpers import schedule_task
from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import done_btn, other_btn
from subiquitycore.ui.container import Columns, ListBox
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.utils import button_pile, Color, screen

from subiquity.common.types import RefreshCheckState

log = logging.getLogger('subiquity.ui.views.refresh')


class TaskProgressBar(ProgressBar):
    def __init__(self):
        super().__init__(
            normal='progress_incomplete',
            complete='progress_complete')
        self._width = 80
        self.label = ""

    def render(self, size, focus=False):
        self._width = size[0]
        return super().render(size, focus)

    def get_text(self):
        current_MiB = self.current / 1024 / 1024
        done_MiB = self.done / 1024 / 1024
        suffix = " {:.2f} / {:.2f} MiB".format(current_MiB, done_MiB)
        remaining = self._width - len(suffix) - 2
        if len(self.label) > remaining:
            label = self.label[:remaining-3] + '...'
        else:
            label = self.label + ' ' * (remaining - len(self.label))
        return label + suffix


class TaskProgress(WidgetWrap):

    def __init__(self):
        self.mode = "spinning"
        self.spinner = Spinner()
        self.label = Text("", wrap='clip')
        cols = Color.progress_incomplete(Columns([
            (1, Text("")),
            self.label,
            (1, Text("")),
            (1, self.spinner),
            (1, Text("")),
            ]))
        super().__init__(cols)

    def update(self, task):
        progress = task['progress']
        done = progress['done']
        total = progress['total']
        if total > 1:
            if self.mode == "spinning":
                bar = TaskProgressBar()
                self._w = bar
            else:
                bar = self._w
            bar.label = task['summary']
            bar.done = total
            bar.current = done
        else:
            self.label.set_text(task['summary'])
            self.spinner.spin()


def exc_message(exc):
    try:
        result = exc.response.json()
    except (AttributeError, json.decoder.JSONDecodeError):
        message = None
    else:
        message = result.get("result", {}).get("message")
    if message is not None:
        return message
    return"Unknown error: {}".format(exc)


class RefreshView(BaseView):

    checking_title = _("Checking for installer update...")
    checking_excerpt = _(
        "Contacting the snap store to check if a new version of the "
        "installer is available."
        )

    check_failed_title = _("Contacting the snap store failed")
    check_failed_excerpt = _(
        "Contacting the snap store failed:"
        )

    available_title = _("Installer update available")
    available_excerpt = _(
        "Version {new} of the installer is now available ({current} is "
        "currently running)."
        )

    progress_title = _("Downloading update...")
    progress_excerpt = _(
        "Please wait while the updated installer is being downloaded. The "
        "installer will restart automatically when the download is complete."
        )

    update_failed_title = _("Update failed")
    update_failed_excerpt = _(
        "Downloading and applying the update:"
        )

    def __init__(self, controller):
        self.controller = controller
        self.check_task = None
        self.spinner = Spinner(self.controller.app.aio_loop, style="dots")

        if self.controller.status.availability == RefreshCheckState.UNKNOWN:
            self.check_state_checking()
        else:
            self.check_state_available()

        super().__init__(self._w)

    def check_state_checking(self):
        self.spinner.start()

        rows = [self.spinner]

        buttons = [
            done_btn(_("Continue without updating"), on_press=self.done),
            other_btn(_("Back"), on_press=self.cancel),
            ]

        self.title = self.checking_title
        self.controller.ui.set_header(self.title)
        self._w = screen(rows, buttons, excerpt=_(self.checking_excerpt))
        self.check_task = schedule_task(self._wait_check_result())

    async def _wait_check_result(self):
        try:
            status = await self.controller.wait_for_check()
        except Exception as e:
            self.check_state_failed(e)
            return
        if status.availability == RefreshCheckState.AVAILABLE:
            self.check_state_available()
        elif self.controller.showing:
            self.done()

    def check_state_failed(self, exc):
        self.spinner.stop()

        rows = [Text(exc_message(exc))]

        buttons = button_pile([
            done_btn(_("Try again"), on_press=self.try_check_again),
            done_btn(_("Continue without updating"), on_press=self.done),
            other_btn(_("Back"), on_press=self.cancel),
            ])
        buttons.base_widget.focus_position = 1

        self.title = self.check_failed_title
        self._w = screen(rows, buttons, excerpt=_(self.check_failed_excerpt))

    def try_check_again(self, sender=None):
        self.controller.snapd_network_changed()
        self.check_state_checking()

    def check_state_available(self, sender=None):
        self.spinner.stop()

        rows = [
            Text(_("You can read the release notes for each version at:")),
            Text(""),
            Text(
                "https://github.com/canonical/subiquity/releases",
                align='center'),
            Text(""),
            Text(
                _("If you choose to update, the update will be downloaded "
                  "and the installation will continue from here."),
                ),
            ]

        buttons = button_pile([
            done_btn(_("Update to the new installer"), on_press=self.update),
            done_btn(_("Continue without updating"),
                     on_press=self.skip_update),
            other_btn(_("Back"), on_press=self.cancel),
            ])
        buttons.base_widget.focus_position = 1

        excerpt = _(self.available_excerpt).format(
            current=self.controller.status.current_snap_version,
            new=self.controller.status.new_snap_version)

        self.title = self.available_title
        self.controller.ui.set_header(self.available_title)
        self._w = screen(rows, buttons, excerpt=excerpt)
        if 'update' in self.controller.answers:
            if self.controller.answers['update']:
                self.update()
            else:
                self.controller.app.aio_loop.call_soon(self.skip_update)

    def update(self, sender=None):
        self.spinner.stop()

        self.lb_tasks = ListBox([])
        self.task_to_bar = {}

        buttons = [
            other_btn(_("Cancel update"), on_press=self.check_state_available),
            ]

        self.controller.ui.set_header(_(self.progress_title))
        self._w = screen(
            self.lb_tasks, buttons, excerpt=_(self.progress_excerpt))
        schedule_task(self._update())

    async def _update(self):
        try:
            change_id = await self.controller.start_update()
        except aiohttp.ClientError as e:
            self.update_failed(exc_message(e))
            return
        while True:
            change = await self.controller.get_progress(change_id)
            if change['status'] == 'Done':
                # Clearly if we got here we didn't get restarted by
                # snapd/systemctl (dry-run mode or logged in via SSH)
                self.controller.app.restart(remove_last_screen=False)
                return
            if change['status'] not in ['Do', 'Doing']:
                self.update_failed(change.get('err', "Unknown error"))
                return
            self.update_progress(change)
            await asyncio.sleep(0.1)

    def try_update_again(self, sender=None):
        self.check_state_available()

    def update_failed(self, msg):
        self.spinner.stop()

        rows = [Text(msg)]

        buttons = button_pile([
            done_btn(_("Try again"), on_press=self.try_update_again),
            done_btn(_("Continue without updating"),
                     on_press=self.skip_update),
            other_btn(_("Back"), on_press=self.cancel),
            ])
        buttons.base_widget.focus_position = 1

        self.title = self.update_failed_title
        self._w = screen(rows, buttons, excerpt=_(self.update_failed_excerpt))

    def update_progress(self, change):
        for task in change['tasks']:
            tid = task['id']
            if task['status'] == "Done":
                bar = self.task_to_bar.get(tid)
                if bar is not None:
                    self.lb_tasks.base_widget.body.remove(bar)
                    del self.task_to_bar[tid]
            if task['status'] == "Doing":
                if tid not in self.task_to_bar:
                    self.task_to_bar[tid] = bar = TaskProgress()
                    self.lb_tasks.base_widget.body.append(bar)
                else:
                    bar = self.task_to_bar[tid]
                bar.update(task)

    def done(self, result=None):
        self.spinner.stop()
        self.controller.done()

    def skip_update(self, result=None):
        # stop attempting the update and move forward
        if self.check_task is not None:
            self.check_task.cancel()
            self.check_task = None
        self.done()

    def cancel(self, result=None):
        self.spinner.stop()
        self.controller.cancel()
