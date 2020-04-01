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
    reset_btn,
    )
from subiquitycore.ui.actionmenu import (
    Action,
    ActionMenu,
    )
from subiquitycore.ui.container import Pile
from subiquitycore.ui.utils import (
    button_pile,
    screen,
    make_action_menu_row,
    Color,
    )
from subiquitycore.ui.table import TableRow, TablePile
from subiquitycore.view import BaseView


log = logging.getLogger("console_conf.views.chooser")


class ChooserView(BaseView):
    title = "Ubuntu Core"
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
            for act in s.actions:
                actions.append(Action(label=act.title,
                                      value=act,
                                      enabled=True))
            menu = ActionMenu(actions)
            connect_signal(menu, 'action', self._system_action, s)
            srow = make_action_menu_row([
                Text(s.label),
                Text(s.model.display_name),
                Text(s.brand.display_name),
                Text("(current)" if s.current else ""),
                menu,
            ], menu)
            trows.append(srow)

        systems_table = TablePile(trows, spacing=2)
        systems_table.bind(heading_table)
        rows = [
            Pile([heading_table, systems_table]),
        ]

        buttons = [
            reset_btn("ABORT", on_press=self.abort),
        ]

        super().__init__(screen(
            rows=rows,
            buttons=button_pile(buttons),
            focus_buttons=False,
            excerpt=self.excerpt))

    def _system_action(self, sender, action, system):
        self.controller.select(system, action)

    def abort(self, result):
        self.controller.cancel()


class ChooserConfirmView(BaseView):
    title = "Ubuntu Core"
    excerpt = ("Summary of the selected action.")

    def __init__(self, controller, selection):
        self.controller = controller

        buttons = [
            danger_btn("CONFIRM", on_press=self.confirm),
            reset_btn("ABORT", on_press=self.abort),
        ]
        using_summary = "System seed of device {} version {} from {}".format(
                          selection.system.model.display_name,
                          selection.system.label,
                          selection.system.brand.display_name
                      )
        summary = [
            TableRow([Text("Action:"), Color.info_error(Text(
                selection.action.title))]),
            TableRow([Text("Using:"), Text(using_summary)]),
        ]
        rows = [
            Pile([Text("")]),
            Pile([TablePile(summary)])
        ]
        super().__init__(screen(
            rows=rows,
            buttons=button_pile(buttons),
            focus_buttons=False,
            excerpt=self.excerpt))

    def abort(self, result):
        self.controller.cancel()

    def confirm(self, result):
        self.controller.confirm()
