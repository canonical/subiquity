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

from gettext import ngettext
import logging

from urwid import Text

from subiquitycore.ui.buttons import danger_btn, other_btn
from subiquitycore.ui.table import (
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import button_pile
from subiquitycore.ui.stretchy import Stretchy

from subiquity.common.filesystem import labels

from .helpers import summarize_device


log = logging.getLogger('subiquity.ui.views.filesystem.delete')


class ConfirmDeleteStretchy(Stretchy):

    def __init__(self, parent, obj):
        self.parent = parent
        self.obj = obj

        lines = [
            Text(_("Do you really want to delete the {desc} {label}?").format(
                desc=labels.desc(obj), label=labels.label(obj))),
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
        elif hasattr(obj, 'partitions') and len(obj.partitions()) > 0:
            n = len(obj.partitions())
            if obj.type == "lvm_volgroup":
                line = ngettext(
                    "It contains 1 logical volume",
                    "It contains {n} logical volumes",
                    n)
            else:
                line = ngettext(
                    "It contains 1 partition",
                    "It contains {n} partitions",
                    n)
            lines.append(Text(line.format(n=n)))
            lines.append(Text(""))
            stretchy_index = len(lines)
            rows = []
            for p, cells in summarize_device(obj):
                if p not in [None, obj]:
                    rows.append(TableRow(cells))
            lines.append(TablePile(rows))
        elif obj.type == "raid" and obj._subvolumes:
            n = len(obj._subvolumes)
            line = ngettext(
                    "It contains 1 volume.",
                    "It contains {n} volumes.",
                    n)
            lines.append(Text(line.format(n=n)))
            lines.append(Text(""))
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
        super().__init__("", widgets, stretchy_index, len(lines)+1)

    def confirm(self, sender=None):
        self.parent.controller.delete(self.obj)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()


class ConfirmReformatStretchy(Stretchy):

    def __init__(self, parent, obj):
        self.parent = parent
        self.obj = obj

        fs = obj.fs()
        if fs is not None:
            title = _(
                "Remove filesystem from {device}"
                ).format(device=labels.desc(obj))
            lines = [
                _(
                    "Do you really want to remove the existing filesystem "
                    "from {device}?"
                    ).format(device=labels.label(obj)),
                "",
            ]
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
            if obj.type == "lvm_volgroup":
                things = _("logical volumes")
            else:
                things = _("partitions")
            # things is either "logical volumes" or "partitions"
            title = _("Remove all {things} from {obj}").format(
                things=things, obj=labels.desc(obj))
            lines = [
                _(
                    "Do you really want to remove all {things} from "
                    "{obj}?").format(
                    things=things, obj=labels.label(obj)),
                "",
            ]
            # XXX summarize partitions here?

        delete_btn = danger_btn(label=_("Reformat"), on_press=self.confirm)
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
        self.parent.controller.reformat(self.obj)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()
