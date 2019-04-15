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
from subiquitycore.ui.buttons import cancel_btn, ok_btn, other_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.form import Toggleable
from subiquitycore.ui.spinner import Spinner
from subiquitycore.ui.utils import button_pile, Padding
from subiquitycore.ui.width import widget_width

log = logging.getLogger("subiquity.views.installprogress")


class MyLineBox(LineBox):
    def format_title(self, title):
        if title:
            return [" ", title, " "]
        else:
            return ""


class ProgressView(BaseView):
    def __init__(self, controller):
        self.controller = controller
        self.spinner = Spinner(controller.loop)

        self.reboot_btn = Toggleable(ok_btn(
            _("Reboot Now"), on_press=self.reboot))
        self.exit_btn = cancel_btn(
            _("Exit To Shell"), on_press=self.quit)
        self.view_log_btn = other_btn(
            _("View full log"), on_press=self.view_log)

        self.event_listbox = ListBox()
        self.event_linebox = MyLineBox(self.event_listbox)
        self.event_buttons = button_pile([self.view_log_btn])
        event_body = [
            ('pack', Text("")),
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

    def add_event(self, text):
        walker = self.event_listbox.base_widget.body
        if len(walker) > 0:
            # Remove the spinner from the line it is currently on, if
            # there is one.
            walker[-1] = walker[-1][0]
        # Add spinner to the line we are inserting.
        new_line = Columns([('pack', Text(text)), ('pack', self.spinner)],
                           dividechars=1)
        self._add_line(self.event_listbox, new_line)

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

    def update_running(self):
        self.reboot_btn.base_widget.set_label(_("Cancel update and reboot"))
        self._set_button_width()

    def update_done(self):
        self.reboot_btn.base_widget.set_label(_("Reboot"))
        self._set_button_width()

    def show_complete(self, include_exit=False, running_updates=False):
        if include_exit:
            btns = [self.view_log_btn, self.exit_btn, self.reboot_btn]
        else:
            btns = [self.view_log_btn, self.reboot_btn]
        self._set_buttons(btns)
        self.event_buttons.base_widget.focus_position = 1
        self.event_pile.base_widget.focus_position = 3

    def reboot(self, btn):
        self.reboot_btn.base_widget.set_label(_("Rebooting..."))
        self.reboot_btn.enabled = False
        self.event_buttons.original_widget._select_first_selectable()
        self.controller.click_reboot()
        self._set_button_width()

    def quit(self, btn):
        self.controller.quit()

    def view_log(self, btn):
        self._w = self.log_pile

    def close_log(self, btn):
        self._w = self.event_pile
