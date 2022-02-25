# Copyright 2015 Canonical, Ltd.
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
    LineBox,
    Text,
    )

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import (
    cancel_btn,
    danger_btn,
    ok_btn,
    other_btn,
    )
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.form import Toggleable
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.utils import button_pile, Padding, rewrap
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.width import widget_width

from subiquity.common.types import ApplicationState


log = logging.getLogger("subiquity.ui.views.installprogress")


class MyLineBox(LineBox):
    def format_title(self, title):
        if title:
            return [" ", title, " "]
        else:
            return ""


class ProgressView(BaseView):

    title = _("Install progress")

    def __init__(self, controller):
        self.controller = controller
        self.ongoing = {}  # context_id -> line containing a spinner

        self.reboot_btn = Toggleable(ok_btn(
            _("Reboot Now"), on_press=self.reboot))
        self.view_error_btn = cancel_btn(
            _("View error report"), on_press=self.view_error)
        self.view_log_btn = other_btn(
            _("View full log"), on_press=self.view_log)
        self.continue_btn = other_btn(
            _("Continue"), on_press=self.continue_)

        self.event_listbox = ListBox()
        self.event_linebox = MyLineBox(self.event_listbox)
        self.event_buttons = button_pile([self.view_log_btn])
        event_body = [
            ('weight', 1, Padding.center_79(self.event_linebox, min_width=76)),
            ('pack', Text("")),
            ('pack', self.event_buttons),
            ('pack', Text("")),
        ]
        self.event_pile = Pile(event_body)

        self.log_listbox = ListBox()
        log_linebox = MyLineBox(self.log_listbox, _("Full installer output"))
        log_body = [
            ('weight', 1, log_linebox),
            ('pack', button_pile([other_btn(_("Close"),
                                  on_press=self.close_log)])),
            ]
        self.log_pile = Pile(log_body)

        super().__init__(self.event_pile)

    def _add_line(self, lb, line):
        lb = lb.base_widget
        walker = lb.body
        at_end = len(walker) == 0 or lb.focus_position == len(walker) - 1
        walker.append(line)
        if at_end:
            lb.set_focus(len(walker) - 1)
            lb.set_focus_valign('bottom')

    def event_start(self, context_id, context_parent_id, message):
        self.event_finish(context_parent_id)
        walker = self.event_listbox.base_widget.body
        spinner = Spinner(self.controller.app.aio_loop)
        spinner.start()
        new_line = Columns([
            ('pack', Text(message)),
            ('pack', spinner),
            ], dividechars=1)
        self.ongoing[context_id] = len(walker)
        self._add_line(self.event_listbox, new_line)

    def event_finish(self, context_id):
        index = self.ongoing.pop(context_id, None)
        if index is None:
            return
        walker = self.event_listbox.base_widget.body
        spinner = walker[index][1]
        spinner.stop()
        walker[index] = walker[index][0]

    def finish_all(self):
        for context_id in list(self.ongoing):
            self.event_finish(context_id)

    def add_log_line(self, text):
        self._add_line(self.log_listbox, Text(text))

    def set_status(self, text):
        self.event_linebox.set_title(text)

    def _set_button_width(self):
        w = 14
        for b, o in self.event_buttons.original_widget.contents:
            w = max(widget_width(b), w)
        self.event_buttons.width = self.event_buttons.min_width = w

    def _set_buttons(self, buttons):
        p = self.event_buttons.original_widget
        p.contents[:] = [(b, p.options('pack')) for b in buttons]
        self._set_button_width()

    def update_for_state(self, state):
        if state == ApplicationState.WAITING:
            self.title = _("Installing system")
            btns = []
        elif state == ApplicationState.NEEDS_CONFIRMATION:
            self.title = _("Installing system")
            btns = []
        elif state == ApplicationState.RUNNING:
            self.title = _("Installing system")
            btns = [self.view_log_btn]
        elif state == ApplicationState.POST_WAIT:
            self.title = _("Installing system")
            btns = [self.view_log_btn]
        elif state == ApplicationState.POST_RUNNING:
            self.title = _("Installing system")
            btns = [self.view_log_btn]
        elif state == ApplicationState.UU_RUNNING:
            self.title = _("Install complete!")
            self.reboot_btn.base_widget.set_label(
                _("Cancel update and reboot"))
            btns = [
                self.view_log_btn,
                self.reboot_btn,
                ]
        elif state == ApplicationState.UU_CANCELLING:
            self.title = _("Install complete!")
            self.reboot_btn.base_widget.set_label(_("Rebooting..."))
            self.reboot_btn.enabled = False
            btns = [
                self.view_log_btn,
                self.reboot_btn,
                ]
        elif state == ApplicationState.DONE:
            self.title = _("Install complete!")
            self.reboot_btn.base_widget.set_label(_("Reboot Now"))
            btns = [
                self.view_log_btn,
                self.reboot_btn,
                ]
        elif state == ApplicationState.ERROR:
            self.title = _('An error occurred during installation')
            self.reboot_btn.base_widget.set_label(_("Reboot Now"))
            self.reboot_btn.enabled = True
            btns = [
                self.view_log_btn,
                self.view_error_btn,
                self.reboot_btn,
                ]
        else:
            raise Exception(state)
        if self.controller.showing:
            self.controller.app.ui.set_header(self.title)
        self._set_buttons(btns)

    def show_continue(self):
        btns = [self.continue_btn, self.reboot_btn]
        self._set_buttons(btns)
        self.event_buttons.base_widget.focus_position = 0
        self.event_pile.base_widget.focus_position = 2

    def continue_(self, sender=None):
        if self.controller.showing:
            self.controller.app.show_confirm_install()
        else:
            self.controller.app.next_screen()

    def hide_continue(self):
        btns = [self.view_log_btn]
        self._set_buttons(btns)
        self.event_buttons.base_widget.focus_position = 0
        self.event_pile.base_widget.focus_position = 2

    def reboot(self, btn):
        log.debug('reboot clicked')
        self.reboot_btn.base_widget.set_label(_("Rebooting..."))
        self.reboot_btn.enabled = False
        self.event_buttons.original_widget._select_first_selectable()
        self.controller.click_reboot()
        self._set_button_width()

    def view_error(self, btn):
        self.controller.app.show_error_report(self.controller.crash_report_ref)

    def view_log(self, btn):
        self._w = self.log_pile

    def close_log(self, btn):
        self._w = self.event_pile


confirmation_text = _("""\
Selecting Continue below will begin the installation process and
result in the loss of data on the disks selected to be formatted.

You will not be able to return to this or a previous screen once
the installation has started.

Are you sure you want to continue?""")


class InstallConfirmation(Stretchy):
    def __init__(self, app):
        self.app = app
        widgets = [
            Text(rewrap(_(confirmation_text))),
            Text(""),
            button_pile([
                cancel_btn(_("No"), on_press=self.cancel),
                danger_btn(_("Continue"), on_press=self.ok)]),
            ]
        super().__init__(
            _("Confirm destructive action"),
            widgets,
            stretchy_index=0,
            focus_index=2)

    def ok(self, sender):
        if isinstance(self.app.ui.body, ProgressView):
            self.app.ui.body.hide_continue()
        self.app.remove_global_overlay(self)
        if self.app.controllers.Progress.showing:
            self.app.aio_loop.create_task(self.app.confirm_install())
        else:
            self.app.next_screen(self.app.confirm_install())

    def cancel(self, sender):
        self.app.remove_global_overlay(self)
        if isinstance(self.app.ui.body, ProgressView):
            self.app.ui.body.show_continue()


running_text = _("""\
The installer running on {tty} is currently installing the system.

You can wait for this to complete or switch to a shell.
""")


class InstallRunning(Stretchy):
    def __init__(self, app, tty):
        self.app = app
        self.btn = Toggleable(other_btn(
                _("Switch to a shell"), on_press=self._debug_shell))
        self.btn.enabled = False
        self.app.aio_loop.call_later(0.5, self._enable)
        widgets = [
            Text(rewrap(_(running_text).format(tty=tty))),
            Text(''),
            button_pile([self.btn]),
            ]
        super().__init__(
            "",
            widgets,
            stretchy_index=0,
            focus_index=2)

    def _enable(self):
        self.btn.enabled = True

    def _debug_shell(self, sender):
        self.app.debug_shell()
