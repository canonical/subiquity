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
from subiquitycore.ui.table import ColSpec, TablePile, TableRow
from subiquitycore.ui.utils import button_pile
from subiquitycore.ui.stretchy import Stretchy

from subiquity.models.filesystem import humanize_size


log = logging.getLogger('subiquity.ui.filesystem.disk_info')


def summarize_partitions(obj):
    # [ label, size, annotations, usage comment ]
    rows = []
    for p in obj.partitions():
        row = [
            Text(p.short_label),
            Text(humanize_size(p.size), align='right'),
            Text(", ".join(p.annotations + p.usage_labels()))
            ]
        rows.append(TableRow(row))
    return TablePile(rows, colspecs={2: ColSpec(can_shrink=True)})


class ConfirmDeleteStretchy(Stretchy):

    def __init__(self, parent, obj):
        self.parent = parent
        self.obj = obj

        title = _("Confirm deletion of {}").format(obj.desc())

        lines = [
            Text(_("Do you really want to delete the {desc} {label}?").format(
                desc=obj.desc(), label=obj.label)),
            Text(""),
        ]
        stretchy_index = 0
        fs = obj.fs()
        if fs is not None:
            m = fs.mount()
            if m is not None:
                lines.append(Text(_(
                    "It is formatted as {fstype} and mounted at "
                    "{path}").format(
                        fstype=fs.fstype,
                        path=m.path)))
            else:
                lines.append(Text(_(
                    "It is formatted as {fstype} and not mounted.").format(
                        fstype=fs.fstype)))
        elif len(obj.partitions()) > 0:
            n = len(obj.partitions())
            if obj.type == "lvm_volgroup":
                if n == 1:
                    things = _("logical volume")
                else:
                    things = _("logical volumes")
            else:
                if n == 1:
                    things = _("partition")
                else:
                    things = _("partitions")
            lines.append(Text(_("It contains {n} {things}:").format(
                n=n, things=things)))
            lines.append(Text(""))
            stretchy_index = len(lines)
            lines.append(summarize_partitions(obj))
        else:
            lines.append(Text(_("It is not formatted or mounted.")))

        delete_btn = danger_btn(label=_("Delete"), on_press=self.confirm)
        widgets = lines + [
            Text(""),
            button_pile([
                delete_btn,
                other_btn(label=_("Cancel"), on_press=self.cancel),
                ]),
        ]
        super().__init__(title, widgets, stretchy_index, len(lines)+1)

    def confirm(self, sender=None):
        self.parent.controller.delete(self.obj)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()
