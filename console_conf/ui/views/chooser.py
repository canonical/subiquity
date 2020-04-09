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

""" Chooser

Chooser provides a view with recovery chooser actions.

"""
import logging

from urwid import (
    connect_signal,
    Text,
    )
from subiquitycore.ui.buttons import (
    danger_btn,
    forward_btn,
    back_btn,
    )
from subiquitycore.ui.actionmenu import (
    Action,
    ActionMenu,
    )
from subiquitycore.ui.container import Pile, ListBox
from subiquitycore.ui.utils import (
    button_pile,
    screen,
    make_action_menu_row,
    Color,
    )
from subiquitycore.ui.table import TableRow, TablePile
from subiquitycore.view import BaseView


log = logging.getLogger("console_conf.views.chooser")


class ChooserBaseView(BaseView):
    title = "Ubuntu Core"

    def __init__(self, current, scr):
        super().__init__(scr)

        if current is not None:
            self.title = current.model.display_name


def by_preferred_action_type(action):
    """Order action entries by having the 'run' mode first, then 'recover', then
    'install', the rest is ordered alphabetically."""
    priority = {"run": 0, "recover": 1, "install": 2}
    return (priority.get(action.mode, 100), action.title.lower())


class ChooserCurrentSystemView(ChooserBaseView):
    excerpt = "Select action:"

    def __init__(self, controller, current, has_more=False):
        self.controller = controller
        log.debug('more systems available: %s', has_more)
        log.debug('current system: %s', current)

        actions = []
        for action in sorted(current.actions, key=by_preferred_action_type):
            actions.append(forward_btn(label=action.title.capitalize(),
                                       on_press=self._current_system_action,
                                       user_arg=(current, action)))

        if has_more:
            # add a button to show the other systems
            actions.append(Text(""))
            actions.append(forward_btn(label="Show all available systems",
                                       on_press=self._more_options))

        lb = ListBox(actions)

        super().__init__(current,
                         screen(
                             lb,
                             narrow_rows=True,
                             excerpt=self.excerpt))

    def _current_system_action(self, sender, arg):
        current, action = arg
        self.controller.select(current, action)

    def _more_options(self, sender):
        self.controller.more_options()

    def back(self, result):
        self.controller.back()


class ChooserView(ChooserBaseView):
    excerpt = ("Select one of available recovery systems and a desired "
               "action to execute.")

    def __init__(self, controller, systems):
        self.controller = controller

        heading_table = TablePile([
            TableRow([
                Color.info_minor(Text(header)) for header in [
                    "LABEL", "MODEL", "PUBLISHER", ""
                    ]
                ])
            ],
            spacing=2)

        trows = []
        systems = sorted(systems,
                         key=lambda s: (s.brand.display_name,
                                        s.model.display_name,
                                        s.current,
                                        s.label))
        for s in systems:
            actions = []
            log.debug('actions: %s', s.actions)
            for act in sorted(s.actions, key=by_preferred_action_type):
                actions.append(Action(label=act.title.capitalize(),
                                      value=act,
                                      enabled=True))
            menu = ActionMenu(actions)
            connect_signal(menu, 'action', self._system_action, s)
            srow = make_action_menu_row([
                Text(s.label),
                Text(s.model.display_name),
                Text(s.brand.display_name),
                Text("(installed)" if s.current else ""),
                menu,
            ], menu)
            trows.append(srow)

        systems_table = TablePile(trows, spacing=2)
        systems_table.bind(heading_table)
        rows = [
            Pile([heading_table, systems_table]),
        ]

        buttons = []
        if controller.model.current is not None:
            # back to options of current system
            buttons.append(back_btn("BACK", on_press=self.back))

        super().__init__(controller.model.current,
                         screen(
                             rows=rows,
                             buttons=button_pile(buttons),
                             focus_buttons=False,
                             excerpt=self.excerpt))

    def _system_action(self, sender, action, system):
        self.controller.select(system, action)

    def back(self, result):
        self.controller.back()


class ChooserConfirmView(ChooserBaseView):

    canned_summary = {
        "run": "Continue running the system without any changes.",
        "recover": ("You have requested to reboot the system into recovery "
                    "mode."),
        "install": ("You are about to {action_lower} the system version "
                    "{version} for {model} from {publisher}.\n\n"
                    "This will remove all existing user data on the "
                    "device.\n\n"
                    "The system will reboot in the process."),
    }
    default_summary = ("You are about to execute action \"{action}\" using "
                       "system version {version} for device {model} from "
                       "{publisher}.\n\n"
                       "Make sure you understand the consequences of "
                       "performing this action.")

    def __init__(self, controller, selection):
        self.controller = controller

        buttons = [
            danger_btn("CONFIRM", on_press=self.confirm),
            back_btn("BACK", on_press=self.back),
        ]
        fmt = self.canned_summary.get(selection.action.mode,
                                      self.default_summary)
        summary = fmt.format(action=selection.action.title,
                             action_lower=selection.action.title.lower(),
                             model=selection.system.model.display_name,
                             publisher=selection.system.brand.display_name,
                             version=selection.system.label)
        rows = [
            Text(summary),
        ]
        super().__init__(controller.model.current,
                         screen(
                             rows=rows,
                             buttons=button_pile(buttons),
                             focus_buttons=False))

    def confirm(self, result):
        self.controller.confirm()

    def back(self, result):
        self.controller.back()
