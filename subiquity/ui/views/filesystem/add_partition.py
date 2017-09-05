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


class PartitionForm(Form):

    def __init__(self, model, max_size, initial={}):
        self.model = model
        super().__init__(initial)
        if max_size is not None:
            self.max_size = max_size
            self.size_str = humanize_size(max_size)
            self.size.caption = "Size (max {})".format(self.size_str)
        else:
            self.remove_field('partnum')
            self.remove_field('size')
        connect_signal(self.fstype.widget, 'select', self.select_fstype)

    def select_fstype(self, sender, fs):
        self.mount.enabled = fs.is_mounted

    partnum = IntegerField("Partition number")
    size = StringField()
    fstype = FSTypeField("Format")
    mount = MountField("Mount")

    def clean_size(self, val):
        if not val:
            return self.max_size
        suffixes = ''.join(HUMAN_UNITS) + ''.join(HUMAN_UNITS).lower()
        if val[-1] not in suffixes:
            unit = self.size_str[-1]
            val += unit
            self.size.widget.value = val
        sz = dehumanize_size(val)
        if sz > self.max_size:
            self.size.show_extra(Color.info_minor(Text("Capped partition size at %s"%(self.size_str,), align="center")))
            self.size.widget.value = self.size_str
            return self.max_size
        return sz

    def clean_mount(self, val):
        if self.fstype.value.is_mounted:
            return val
        else:
            return None

    def validate_mount(self):
        mount = self.mount.value
        if mount is not None:
            return self.model.validate_mount(mount)


class PartitionFormatView(BaseView):
    def __init__(self, size, initial, back):
        self.form = PartitionForm(self.model, size, initial)

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
        self.back()


class AddPartitionView(PartitionFormatView):

    def __init__(self, model, controller, disk):
        log.debug('AddPartitionView: selected_disk=[{}]'.format(disk.path))
        self.model = model
        self.controller = controller
        self.disk = disk
        super().__init__(disk.free, {'partnum': disk.next_partnum}, lambda : self.controller.partition_disk(disk))

    def done(self, form):
        log.debug("Add Partition Result: {}".format(form.as_data()))
        self.controller.add_disk_partition_handler(self.disk, form.as_data())


class AddFormatView(PartitionFormatView):
    def __init__(self, model, controller, volume, back):
        self.model = model
        self.controller = controller
        self.volume = volume
        self.back = back

        initial = {}
        fs = self.volume.fs()
        if fs is not None:
            initial['fstype'] = self.model.fs_by_name[fs.fstype]
        super().__init__(None, initial, self.back)

    def done(self, form):
        log.debug("Add Partition Result: {}".format(form.as_data()))
        self.controller.add_format_handler(self.volume, form.as_data(), self.back)
