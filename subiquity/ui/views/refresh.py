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
    ProgressBar,
    Text,
    WidgetWrap,
    )

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import done_btn, other_btn
from subiquitycore.ui.container import Columns, ListBox
from subiquitycore.ui.utils import button_pile, Color, screen

from subiquity.controllers.refresh import CheckState
from subiquity.ui.spinner import Spinner

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


class RefreshView(BaseView):

    checking_title = _("Checking for installer update...")
    checking_excerpt = _(
        "Contacting the snap store to check if a new version of the "
        "installer is available."
        )

    failed_title = _("Contacting the snap store failed")
    failed_excerpt = _(
        "Contacting the snap store failed:"
        )

    available_title = _("Installer update available")
    available_excerpt = _(
        "A new version of the installer is available."
        )

    progress_title = _("Downloading update...")
    progress_excerpt = _(
        "Please wait while the updated installer is being downloaded. The "
        "installer will restart automatically when the download is complete."
        )

    def __init__(self, controller):
        self.controller = controller
        self.spinner = Spinner(self.controller.loop, style="dots")

        if self.controller.check_state == CheckState.CHECKING:
            self.check_state_checking()
        elif self.controller.check_state == CheckState.AVAILABLE:
            self.check_state_available()
        else:
            raise AssertionError(
                "instantiating the view with check_state {}".format(
                    self.controller.check_state))

        super().__init__(self._w)

    def update_check_state(self):
        if self.controller.check_state == CheckState.UNAVAILABLE:
            self.done()
        elif self.controller.check_state == CheckState.FAILED:
            self.check_state_failed()
        elif self.controller.check_state == CheckState.AVAILABLE:
            self.check_state_available()
        else:
            raise AssertionError(
                "update_check_state with check_state {}".format(
                    self.controller.check_state))

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

    def check_state_available(self, sender=None):
        self.spinner.stop()

        rows = [
            Text(
                _("If you choose to update, the update will be downloaded "
                  "and the installation will continue from here."),
                )
            ]

        buttons = button_pile([
            done_btn(_("Update to the new installer"), on_press=self.update),
            done_btn(_("Continue without updating"), on_press=self.done),
            other_btn(_("Back"), on_press=self.cancel),
            ])
        buttons.base_widget.focus_position = 1

        self.title = self.available_title
        self.controller.ui.set_header(self.available_title)
        self._w = screen(rows, buttons, excerpt=_(self.available_excerpt))

    def check_state_failed(self):
        self.spinner.stop()

        rows = [Text("<explanation goes here>")]

        buttons = button_pile([
            done_btn(_("Try again"), on_press=self.still_checking),
            done_btn(_("Continue without updating"), on_press=self.done),
            other_btn(_("Back"), on_press=self.cancel),
            ])
        buttons.base_widget.focus_position = 1

        self.title = self.failed_title
        self._w = screen(rows, buttons, excerpt=_(self.failed_excerpt))

    def update(self, sender=None):
        self.spinner.stop()

        self.lb_tasks = ListBox([])
        self.task_to_bar = {}

        buttons = [
            other_btn(_("Cancel update"), on_press=self.check_state_available),
            ]

        self.controller.ui.set_header("Downloading update...")
        self._w = screen(
            self.lb_tasks, buttons, excerpt=_(self.progress_excerpt))
        self.controller.start_update(self.update_started)

    def update_started(self, change_id):
        self.change_id = change_id
        self.update_progress()

    def update_progress(self, loop=None, ud=None):
        self.controller.get_progress(self.change_id, self.updated_progress)

    def updated_progress(self, change):
        if change['status'] == 'Done':
            # Will only get here dry run mode as part of the refresh is us
            # getting restarted by snapd...
            self.done()
            return
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
        self.controller.loop.set_alarm_in(0.1, self.update_progress)

    def done(self, result=None):
        self.spinner.stop()
        self.controller.done()

    def cancel(self, result=None):
        self.spinner.stop()
        self.controller.cancel()
