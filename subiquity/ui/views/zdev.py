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

""" zdev

Provides device activation and configuration on s390x

"""
import logging

from urwid import (
    connect_signal,
    Text,
    )

from subiquitycore.ui.actionmenu import (
    ActionMenu,
    )
from subiquitycore.ui.buttons import (
    back_btn,
    done_btn,
    )
from subiquitycore.ui.container import (
    ListBox,
    WidgetWrap,
    )
from subiquitycore.ui.table import (
    ColSpec,
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    Color,
    make_action_menu_row,
    screen,
    )
from subiquitycore.view import BaseView

log = logging.getLogger('subiquity.ui.zdev')


class ZdevList(WidgetWrap):

    def __init__(self, parent):
        self.parent = parent
        self.table = TablePile([], spacing=2, colspecs={
            0: ColSpec(rpad=2),
            1: ColSpec(rpad=2),
            2: ColSpec(rpad=2),
            3: ColSpec(rpad=2),
        })
        self._no_zdev_content = Color.info_minor(
            Text(_("No zdev devices found.")))
        super().__init__(self.table)

    def _zdev_action(self, sender, action, zdevinfo):
        if action in ('disable', 'enable'):
            self.parent.controller.chzdev(action, zdevinfo)
            self.parent.refresh_model_inputs()

    def refresh_model_inputs(self):
        zdevinfos = self.parent.controller.get_zdevinfos()

        rows = [TableRow([
            Color.info_minor(heading) for heading in [
                Text(_("ID")),
                Text(_("ONLINE")),
                Text(_("NAMES")),
            ]])]

        typeclass = ''
        for i, zdevinfo in enumerate(zdevinfos):
            if zdevinfo.typeclass != typeclass:
                rows.append(TableRow([
                    Text(""),
                ]))
                rows.append(TableRow([
                    Color.info_minor(Text(zdevinfo.type)),
                    Text(""),
                    Text("")
                ]))
                typeclass = zdevinfo.typeclass

            if zdevinfo.type == 'zfcp-lun':
                rows.append(TableRow([
                    Color.info_minor(Text(zdevinfo.id[9:])),
                    zdevinfo.status,
                    Text(zdevinfo.names),
                ]))
                continue

            actions = [(_("Enable"), not zdevinfo.on, 'enable'),
                       (_("Disable"), zdevinfo.on, 'disable')]
            menu = ActionMenu(actions)
            connect_signal(menu, 'action', self._zdev_action, zdevinfo)
            cells = [
                Text(zdevinfo.id),
                zdevinfo.status,
                Text(zdevinfo.names),
                menu,
            ]
            row = make_action_menu_row(
                cells,
                menu,
                attr_map='menu_button',
                focus_map={
                    None: 'menu_button focus',
                    'info_minor': 'menu_button focus',
                })
            rows.append(row)
        self.table.set_contents(rows)
        if self.table._w.focus_position >= len(rows):
            self.table._w.focus_position = len(rows) - 1


class ZdevView(BaseView):
    title = _("Zdev setup")

    def __init__(self, controller):
        log.debug('FileSystemView init start()')
        self.controller = controller
        self.zdev_list = ZdevList(self)

        body = [
            self.zdev_list,
            Text(""),
            ]

        self.lb = ListBox(body, always_scroll=True)
        frame = screen(
            self.lb, self._build_buttons(),
            focus_buttons=False)
        super().__init__(frame)
        self.refresh_model_inputs()

    def _build_buttons(self):
        return [
            done_btn(_("Continue"), on_press=self.done),
            back_btn(_("Back"), on_press=self.cancel),
            ]

    def refresh_model_inputs(self):
        self.zdev_list.refresh_model_inputs()

    def cancel(self, button=None):
        self.controller.cancel()

    def done(self, result):
        self.controller.done()
