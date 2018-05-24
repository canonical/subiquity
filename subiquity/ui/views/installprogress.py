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
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import button_pile, Padding

from subiquity.ui.spinner import Spinner

log = logging.getLogger("subiquity.views.installprogress")


class MyLineBox(LineBox):
    def format_title(self, title):
        if title:
            return [" ", title, " "]
        else:
            return ""


class AskForRetryStretchy(Stretchy):
    def __init__(self, parent, watcher, snap_name, explanation):
        self.parent = parent
        self.watcher = watcher
        if explanation is None:
            widgets = [
                Text(_('Downloading the snap "{}" failed for an unknown '
                       'reason.').format(snap_name)),
                ]
            stretchy_index = 0
        else:
            widgets = [
                Text(_('Downloading the snap "{}" failed with the following '
                       'output:').format(snap_name)),
                Text(""),
                Text(explanation),
                ]
            stretchy_index = 2
        retry = other_btn(
            label=_("Try again"),
            on_press=self.cont, user_arg=True)
        give_up = other_btn(
            label=_("Give up on this snap"),
            on_press=self.cont, user_arg=False)
        widgets.extend([
            Text(""),
            Text(_("Would you like to try to download this snap again?")),
            Text(""),
            button_pile([retry, give_up]),
            ])
        title = _('Downloading "{}" failed.').format(snap_name)
        super().__init__(title, widgets, stretchy_index, len(widgets) - 1)

    def cont(self, sender, retry_cur):
        self.parent.remove_overlay()
        self.parent.controller.resume_snap_downloads(self.watcher, retry_cur)


class ProgressView(BaseView):
    def __init__(self, controller):
        self.controller = controller
        self.spinner = Spinner(controller.loop)

        self.event_listbox = ListBox()
        self.event_linebox = MyLineBox(self.event_listbox)
        self.event_buttons = button_pile([other_btn(_("View full log"),
                                          on_press=self.view_log)])
        event_body = [
            ('pack', Text("")),
            ('weight', 1, Padding.center_79(self.event_linebox)),
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

    def show_complete(self, include_exit=False):
        p = self.event_buttons.original_widget
        p.contents.append(
            (ok_btn(_("Reboot Now"), on_press=self.reboot),
             p.options('pack')))
        if include_exit:
            p.contents.append(
                (cancel_btn(_("Exit To Shell"), on_press=self.quit),
                 p.options('pack')))

        w = 0
        for b, o in p.contents:
            w = max(len(b.base_widget.label), w)
        self.event_buttons.width = self.event_buttons.min_width = w + 4
        self.event_pile.focus_position = 3
        p.focus_position = 1

    def ask_for_retry_snap(self, watcher, snap_name, explanation):
        self.show_stretchy_overlay(
            AskForRetryStretchy(self, watcher, snap_name, explanation))

    def reboot(self, btn):
        self.controller.reboot()

    def quit(self, btn):
        self.controller.quit()

    def view_log(self, btn):
        self._w = self.log_pile

    def close_log(self, btn):
        self._w = self.event_pile
