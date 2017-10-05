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

from subiquitycore.ui.buttons import delete_btn
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
    FilesystemModel,
    HUMAN_UNITS,
    dehumanize_size,
    humanize_size,
    )
from subiquity.ui.mount import MountField


log = logging.getLogger('subiquity.ui.filesystem.add_partition')


class FSTypeField(FormField):
    def _make_widget(self, form):
        return Selector(opts=FilesystemModel.supported_filesystems)


class PartitionForm(Form):

    def __init__(self, mountpoint_to_devpath_mapping, max_size, initial={}):
        self.mountpoint_to_devpath_mapping = mountpoint_to_devpath_mapping
        super().__init__(initial)
        if max_size is not None:
            self.max_size = max_size
            self.size_str = humanize_size(max_size)
            self.size.caption = "Size (max {})".format(self.size_str)
        else:
            self.remove_field('partnum')
            self.remove_field('size')
        connect_signal(self.fstype.widget, 'select', self.select_fstype)
        self.select_fstype(None, self.fstype.widget.value)

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
            self.size.show_extra(('info_minor', "Capped partition size at %s"%(self.size_str,)))
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
        if mount is None:
            return
        # /usr/include/linux/limits.h:PATH_MAX
        if len(mount) > 4095:
            return 'Path exceeds PATH_MAX'
        dev = self.mountpoint_to_devpath_mapping.get(mount)
        if dev is not None:
            return "%s is already mounted at %s"%(dev, mount)


class PartitionFormatView(BaseView):

    form_cls = PartitionForm

    def __init__(self, size, existing, initial, back):

        mountpoint_to_devpath_mapping = self.model.get_mountpoint_to_devpath_mapping()
        if existing is not None:
            fs = existing.fs()
            if fs is not None:
                initial['fstype'] = self.model.fs_by_name[fs.fstype]
                mount = fs.mount()
                if mount is not None:
                    initial['mount'] = mount.path
                    if mount.path in mountpoint_to_devpath_mapping:
                        del mountpoint_to_devpath_mapping[mount.path]
            else:
                initial['fstype'] = self.model.fs_by_name[None]
        self.form = self.form_cls(mountpoint_to_devpath_mapping, size, initial)
        self.back = back

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        partition_box = Padding.center_50(ListBox(self.make_body()))
        super().__init__(partition_box)

    def make_body(self):
        return [
            self.form.as_rows(self),
            Padding.line_break(""),
            self.form.buttons,
        ]

    def cancel(self, button=None):
        self.back()


class PartitionView(PartitionFormatView):

    def __init__(self, model, controller, disk, partition=None):
        log.debug('PartitionView: selected_disk=[{}]'.format(disk.path))
        self.model = model
        self.controller = controller
        self.disk = disk
        self.partition = partition

        max_size = disk.free
        if partition is None:
            initial = {'partnum': disk.next_partnum}
            label = _("Create")
        else:
            max_size += partition.size
            initial = {
                'partnum': partition.number,
                'size': humanize_size(partition.size),
                }
            label = _("Save")
        super().__init__(max_size, partition, initial, lambda : self.controller.partition_disk(disk))
        self.form.buttons.base_widget[0].set_label(label)

    def make_body(self):
        body = super().make_body()
        if self.partition is not None:
            btn = delete_btn(on_press=self.delete)
            body[-2:-2] = [
                Text(""),
                Padding.fixed_10(btn),
                ]
            pass
        return body

    def delete(self, sender):
        self.controller.delete_partition(self.partition)

    def done(self, form):
        log.debug("Add Partition Result: {}".format(form.as_data()))
        self.controller.partition_disk_handler(self.disk, self.partition, form.as_data())


class FormatEntireView(PartitionFormatView):
    def __init__(self, model, controller, volume, back):
        self.model = model
        self.controller = controller
        self.volume = volume
        super().__init__(None, volume, {}, back)

    def done(self, form):
        log.debug("Add Partition Result: {}".format(form.as_data()))
        self.controller.add_format_handler(self.volume, form.as_data(), self.back)
