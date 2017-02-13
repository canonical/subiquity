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

""" Filesystem

Provides storage device selection and additional storage
configuration.

"""
import logging
import re
from urwid import connect_signal, Text

from subiquitycore.ui.container import Columns, ListBox
from subiquitycore.ui.form import (
    BoundFormField,
    Form,
    FormField,
    IntegerField,
    StringField,
    )
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.ui.interactive import Selector
from subiquitycore.view import BaseView

from subiquity.models.filesystem import (
    _humanize_size,
    _dehumanize_size,
    HUMAN_UNITS,
    )
from subiquity.ui.mount import MountSelector


log = logging.getLogger('subiquity.ui.filesystem.add_partition')


class BoundFSTypeField(BoundFormField):
    def _make_widget(self):
        return Selector(opts=self.form.model.supported_filesystems)

class FSTypeField(FormField):
    bound_class = BoundFSTypeField


class BoundMountField(BoundFormField):
    def _make_widget(self):
        return MountSelector(self.form.model)

class MountField(FormField):
    bound_class = BoundMountField


class AddPartitionForm(Form):

    def __init__(self, model, disk_obj):
        self.model = model
        self.disk_obj = disk_obj
        self.size_str = _humanize_size(disk_obj.freespace)
        super().__init__()
        self.size.caption = "Size (max {})".format(self.size_str)
        self.partnum.value = self.disk_obj.lastpartnumber + 1

    partnum = IntegerField("Partition number")
    size = StringField()
    fstype = FSTypeField("Format")
    mount = MountField("Mount")

    def validate_size(self):
        v = self.size.value
        if not v:
            return
        r = '(\d+[\.]?\d*)([{}])?$'.format(''.join(HUMAN_UNITS))
        match = re.match(r, v)
        if not match:
            return "Invalid partition size"
        unit = match.group(2)
        if unit is None:
            unit = self.size_str[-1]
            v += unit
            self.size.value = v
        sz = _dehumanize_size(v)
        if sz > self.disk_obj.freespace:
            self.size.value = self.size_str
            self.size.show_extra(Color.info_minor(Text("Capped partition size at %s"%(self.size_str,))))

    def validate_mount(self):
        mnts = self.model.get_mounts2()
        dev = mnts.get(self.mount.value)
        if dev is not None:
            return "%s is already mounted at %s"%(dev, self.mount.value)


class AddPartitionView(BaseView):

    def __init__(self, model, controller, selected_disk):
        log.debug('AddPartitionView: selected_disk=[{}]'.format(selected_disk))
        self.model = model
        self.controller = controller
        self.selected_disk = selected_disk
        self.disk_obj = self.model.get_disk(selected_disk)

        self.form = AddPartitionForm(model, self.disk_obj)

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)
        connect_signal(self.form.fstype.widget, 'select', self.select_fstype)

        body = [
            Columns(
                [
                    ("weight", 0.2, Text("Adding partition to {}".format(
                        self.disk_obj.devpath), align="right")),
                    ("weight", 0.3, Text(""))
                ]
            ),
            Padding.line_break(""),
            self.form.as_rows(),
            Padding.line_break(""),
            Padding.fixed_10(self.form.buttons),
        ]
        partition_box = Padding.center_50(ListBox(body))
        super().__init__(partition_box)

    def _enable_disable_mount(self, enabled):
        if enabled:
            self.form.mount.enable()
        else:
            self.form.mount.disable()

    def select_fstype(self, sender, fs):
        if fs.is_mounted != sender.value.is_mounted:
            self._enable_disable_mount(fs.is_mounted)

    def cancel(self, button):
        self.controller.prev_view()

    def done(self, result):

        fstype = self.form.fstype.value

        if fstype.is_mounted:
            mount = self.form.mount.value
        else:
            mount = None

        if self.form.size.value:
            size = _dehumanize_size(self.form.size.value)
            if size > self.disk_obj.freespace:
                size = self.disk_obj.freespace
        else:
            size = self.disk_obj.freespace

        result = {
            "partnum": self.form.partnum.value,
            "raw_size": self.form.size.value,
            "bytes": size,
            "fstype": fstype.label,
            "mountpoint": mount,
        }

        log.debug("Add Partition Result: {}".format(result))
        self.controller.add_disk_partition_handler(self.disk_obj.devpath, result)
