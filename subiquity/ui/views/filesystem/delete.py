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

import logging
from urwid import Text

from subiquitycore.ui.buttons import danger_btn, other_btn
from subiquitycore.ui.utils import button_pile
from subiquitycore.ui.stretchy import Stretchy


log = logging.getLogger('subiquity.ui.filesystem.disk_info')


class ConfirmDeleteStretchy(Stretchy):

    def __init__(self, parent, obj):
        self.parent = parent
        self.obj = obj

        title = _("Confirm deletion of {}").format(obj.desc())

        lines = [
            _("Do you really want to delete {}?").format(obj.label),
            "",
        ]
        fs = obj.fs()
        if fs is not None:
            m = fs.mount()
            if m is not None:
                lines.append(_(
                    "It is formatted as {fstype} and mounted at "
                    "{path}").format(
                        fstype=fs.fstype,
                        path=m.path))
            else:
                lines.append(_(
                    "It is formatted as {fstype} and not mounted.").format(
                        fstype=fs.fstype))
        else:
            lines.append(_("It is not formatted or mounted."))
        delete_btn = danger_btn(label=_("Delete"), on_press=self.confirm)
        widgets = [
            Text("\n".join(lines)),
            Text(""),
            button_pile([
                delete_btn,
                other_btn(label=_("Cancel"), on_press=self.cancel),
                ]),
        ]
        super().__init__(title, widgets, 0, 2)

    def confirm(self, sender=None):
        self.parent.controller.delete(self.obj)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()
