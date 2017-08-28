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
from urwid import connect_signal, Text

from subiquitycore.ui.container import ListBox
from subiquitycore.ui.form import (
    Form,
    FormField,
    IntegerField,
    StringField,
    )
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.ui.interactive import Selector
from subiquitycore.view import BaseView

from subiquity.models.filesystem import (
    humanize_size,
    dehumanize_size,
    HUMAN_UNITS,
    )
from subiquity.ui.mount import MountField


log = logging.getLogger('subiquity.ui.filesystem.add_partition')


class FSTypeField(FormField):
    def _make_widget(self, form):
        return Selector(opts=form.model.supported_filesystems)


class AddPartitionForm(Form):

    def __init__(self, model, disk):
        self.model = model
        self.disk = disk
        self.size_str = humanize_size(disk.free)
        super().__init__()
        self.size.caption = "Size (max {})".format(self.size_str)
        self.partnum.value = self.disk.next_partnum
        connect_signal(self.fstype.widget, 'select', self.select_fstype)

    def select_fstype(self, sender, fs):
        self.mount.enabled = fs.is_mounted

    partnum = IntegerField("Partition number")
    size = StringField()
    fstype = FSTypeField("Format")
    mount = MountField("Mount")

    def validate_size(self):
        v = self.size.value
        if not v:
            return
        suffixes = ''.join(HUMAN_UNITS) + ''.join(HUMAN_UNITS).lower()
        if v[-1] not in suffixes:
            unit = self.size_str[-1]
            v += unit
            self.size.value = v
        try:
            sz = dehumanize_size(v)
        except ValueError as v:
            return str(v)
        if sz > self.disk.free:
            self.size.value = self.size_str
            self.size.show_extra(Color.info_minor(Text("Capped partition size at %s"%(self.size_str,), align="center")))

    def validate_mount(self):
        return self.model.validate_mount(self.mount.value)


class AddPartitionView(BaseView):

    def __init__(self, model, controller, disk):
        log.debug('AddPartitionView: selected_disk=[{}]'.format(disk.path))
        self.model = model
        self.controller = controller
        self.disk = disk

        self.form = AddPartitionForm(model, self.disk)

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        body = [
            self.form.as_rows(self),
            Padding.line_break(""),
            Padding.fixed_10(self.form.buttons),
        ]
        partition_box = Padding.center_50(ListBox(body))
        super().__init__(partition_box)

    def cancel(self, button=None):
        self.controller.partition_disk(self.disk)

    def done(self, result):

        fstype = self.form.fstype.value

        if fstype.is_mounted:
            mount = self.form.mount.value
        else:
            mount = None

        if self.form.size.value:
            size = dehumanize_size(self.form.size.value)
            if size > self.disk.free:
                size = self.disk.free
        else:
            size = self.disk.free

        result = {
            "partnum": self.form.partnum.value,
            "bytes": size,
            "fstype": fstype.label,
            "mountpoint": mount,
        }

        log.debug("Add Partition Result: {}".format(result))
        self.controller.add_disk_partition_handler(self.disk, result)
