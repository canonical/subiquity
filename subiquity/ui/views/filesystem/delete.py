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
from urwid import Text, WidgetDisable

from subiquitycore.ui.buttons import danger_btn, other_btn
from subiquitycore.ui.utils import button_pile, Color
from subiquitycore.ui.stretchy import Stretchy

from subiquity.models.filesystem import (
    _Device,
    Raid,
    raidlevels_by_value,
)


log = logging.getLogger('subiquity.ui.filesystem.disk_info')


def can_delete(obj, obj_desc=_("it")):
    if isinstance(obj, _Device):
        for p in obj.partitions():
            ok, reason = can_delete(
                p, obj_desc=_("partition {}").format(p._number))
            if not ok:
                return False, reason
    cd = obj.constructed_device()
    if cd is None:
        return True, ""
    if isinstance(cd, Raid):
        rl = raidlevels_by_value[cd.raidlevel]
        if len(cd.devices) > rl.min_devices:
            return True, ""
        else:
            reason = _("deleting {obj} would leave the {desc} {label} with "
                       "less than {min_devices} devices.").format(
                        obj=_(obj_desc),
                        desc=cd.desc(),
                        label=cd.label,
                        min_devices=rl.min_devices)
            return False, reason
    else:
        raise Exception("unexpected constructed device {}".format(cd.label))


def make_device_remover(cd, obj):

    def remover():
        cd.devices.remove(obj)
        obj._constructed_device = None
    return remover


def make_device_deleter(controller, obj):
    meth = getattr(controller, 'delete_' + obj.type)

    def remover():
        meth(obj)
    return remover


def delete_consequences(controller, obj, obj_desc=_("It")):
    log.debug("building consequences for deleting %s", obj.label)
    deleter = (
        "delete {} {}".format(obj.type, obj.label),
        make_device_deleter(controller, obj),
    )
    if isinstance(obj, _Device):
        if len(obj.partitions()) > 0:
            lines = [_("Proceeding will delete the following partitions:"), ""]
            delete_funcs = []
            for p in obj.partitions():
                desc = _("Partition {}, which").format(p._number)
                new_lines, new_delete_funcs = delete_consequences(
                    controller, p, desc)
                lines.extend(new_lines)
                lines.append("")
                delete_funcs.extend(new_delete_funcs)
            return lines[:-1], delete_funcs + [deleter]
        unused_desc = _("{} is not formatted, partitioned, or part of any "
                        "constructed device.").format(obj_desc)
    else:
        unused_desc = _("{} is not formatted or part of any constructed "
                        "device.").format(obj_desc)
    fs = obj.fs()
    cd = obj.constructed_device()
    if fs is not None:
        desc = _("{} is formatted as {}").format(obj_desc, fs.fstype)
        if fs.mount():
            desc += _(" and mounted at {}.").format(fs.mount().path)
        else:
            desc += _(" and not mounted.")
        return [desc], [deleter]
    elif cd is not None:
        if isinstance(cd, Raid):
            delete_funcs = [(
                "remove {} from {}".format(obj.label, cd.name),
                make_device_remover(cd, obj),
                ),
                deleter,
            ]
            return [
                _("{} is part of the {} {}. {} will be left with {} "
                  "devices.").format(
                    obj_desc,
                    cd.desc(),
                      cd.label,
                      cd.label,
                      len(cd.devices) - 1),
                ], delete_funcs
        else:
            raise Exception(
                "unexpected constructed device {}".format(cd.label))
    else:
        return [unused_desc], [deleter]


class ConfirmDeleteStretchy(Stretchy):

    def __init__(self, parent, obj):
        self.parent = parent
        self.obj = obj

        delete_ok, reason = can_delete(obj)
        if delete_ok:
            title = _("Confirm deletion of {}").format(obj.desc())

            lines = [
                _("Do you really want to delete {}?").format(obj.label),
                "",
            ]
            new_lines, delete_funcs = delete_consequences(
                self.parent.controller, obj)
            lines.extend(new_lines)
            self.delete_funcs = delete_funcs
        else:
            title = "Cannot delete {}".format(obj.desc())
            lines = [
                _("Cannot delete {} because {}").format(obj.label, reason)]
        delete_btn = danger_btn(label=_("Delete"), on_press=self.confirm)
        if not delete_ok:
            delete_btn = WidgetDisable(
                Color.info_minor(
                    delete_btn.original_widget))
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
        for desc, func in self.delete_funcs:
            log.debug("executing delete_func %s", desc)
            func()
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()
