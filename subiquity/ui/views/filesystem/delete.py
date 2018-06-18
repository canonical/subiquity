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

from subiquity.models.filesystem import (
    Partition,
)


log = logging.getLogger('subiquity.ui.filesystem.disk_info')


class ConfirmDeleteStretchy(Stretchy):

    def __init__(self, parent, thing, delete_func):
        self.parent = parent
        self.thing = thing
        self.delete_func = delete_func

        title = _("Confirm deletion of {}").format(thing.desc())

        lines = [
            _("Do you really want to delete {}?").format(thing.label),
        ]
        if isinstance(thing, Partition):
            lines.append("")
            if thing.fs():
                fs = thing.fs()
                desc = _("It is formatted as {}").format(fs.fstype)
                if fs.mount():
                    desc += _(" and mounted at {}.").format(fs.mount().path)
                else:
                    desc += _(" and not mounted.")
            else:
                desc = _("It is not formatted.")
            lines.append(desc)
        else:
            raise Exception(
                "deletion of {} not yet supported".format(thing.desc()))
        widgets = [
            Text("\n".join(lines)),
            Text(""),
            button_pile([
                danger_btn(label=_("Delete"), on_press=self.confirm),
                other_btn(label=_("Cancel"), on_press=self.cancel),
                ]),
        ]
        super().__init__(title, widgets, 0, 2)

    def confirm(self, sender=None):
        self.delete_func(self.thing)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()
