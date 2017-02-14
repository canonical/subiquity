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
from urwid import Text

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import menu_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.interactive import (StringEditor, YesNo,
                                          PasswordEditor)
from subiquitycore.ui.utils import Color, Padding

log = logging.getLogger('subiquity.iscsi')


class IscsiDiskView(BaseView):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
        self.iscsi_host = StringEditor()
        self.connect_anon = YesNo()
        self.connect_username = StringEditor()
        self.connect_password = PasswordEditor()
        self.server_auth = YesNo()
        self.server_username = StringEditor()
        self.server_password = PasswordEditor()
        body = [
            Padding.center_50(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_50(self._build_menu()),
            Padding.line_break(""),
            Padding.center_75(self._build_volume_mount_selector())
        ]
        super().__init__(ListBox(body))

    def _build_model_inputs(self):
        items = [
            Columns(
                [
                    ("weight", 0.2, Text("iSCSI Server Host", align="right")),
                    ("weight", 0.3, Color.string_input(self.iscsi_host))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Connect anonymously", align="right")),
                    ("weight", 0.3, Color.string_input(Pile(self.connect_anon.group)))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Connect as user", align="right")),
                    ("weight", 0.3, Color.string_input(self.connect_username))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Password", align="right")),
                    ("weight", 0.3, Color.string_input(self.connect_password))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Require server auth", align="right")),
                    ("weight", 0.3, Color.string_input(Pile(self.server_auth.group)))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Server identity", align="right")),
                    ("weight", 0.3, Color.string_input(self.server_username))
                ],
                dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Server password", align="right")),
                    ("weight", 0.3, Color.string_input(self.server_password))
                ],
                dividechars=4
            )
        ]
        return Pile(items)

    def _build_menu(self):
        items = []
        for label, sig in self.model.get_menu():
            items.append(
                Columns(
                    [
                        ("weight", 0.2, Text("")),
                        ("weight", 0.3,
                         Color.menu_button(
                             menu_btn(label=label,
                                      on_press=self.confirm,
                                      user_data=sig)))
                    ]))
        return Pile(items)

    def _build_volume_mount_selector(self):
        items = [Text("SELECT VOLUME TO MOUNT")]
        # TODO: List found volumes
        return Pile(items)

    def confirm(self, result):
        self.signal.emit_signal(sig)
