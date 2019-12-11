# Copyright 2017 Canonical, Ltd.
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

from urwid import (
    connect_signal,
    emit_signal,
    RadioButton,
    Text,
    )

from subiquitycore.ui.container import (
    WidgetWrap,
    )
from subiquitycore.ui.form import (
    BooleanField,
    Form,
    NO_CAPTION,
    RadioButtonField,
    simple_field,
    SubForm,
    SubFormField,
    WantsToKnowFormField,
    )
from subiquitycore.ui.table import (
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    Color,
    )
from subiquitycore.view import BaseView

from subiquity.models.filesystem import (
    DeviceAction,
    dehumanize_size,
    )

from .helpers import summarize_device

log = logging.getLogger("subiquity.ui.views.filesystem.guided")

text = _("""The installer can guide you through partitioning an entire disk \
either directly or using LVM, with or without LUKS, or, if you prefer, you \
can do it manually.

If you choose to partition an entire disk you will still have a chance to \
review and modify the results.""")


class DiskChooser(WidgetWrap, WantsToKnowFormField):
    signals = ['change']

    def __init__(self):
        self.table = TablePile([], spacing=1)
        super().__init__(self.table)
        self.value = None

    def _state_change(self, sender, state, disk):
        emit_signal(self, "change", self, disk)
        self.value = disk

    def set_bound_form_field(self, bff):
        model = bff.form.parent.model
        rows = []
        group = []
        for disk in model.all_disks():
            for obj, cells in summarize_device(disk):
                if obj is disk:
                    if self.value is None:
                        self.value = disk
                    but = RadioButton(
                        group=group, label='',
                        on_state_change=self._state_change, user_data=disk)
                    cells.insert(0, but)
                    a = Color.menu_button
                else:
                    cells.insert(0, Text(""))
                    a = Color.info_minor
                rows.append(a(TableRow(cells)))
        self.table.set_contents(rows)


DiskField = simple_field(DiskChooser)
DiskField.takes_default_style = False


class GuidedChoiceForm(SubForm):

    disk_choice = DiskField(caption=NO_CAPTION)
    use_lvm = BooleanField(_("Set up this disk as an LVM group"))


class GuidedForm(Form):

    radio_group = []
    guided_layout = RadioButtonField(radio_group, _("Use an entire disk"))
    disk_choice = SubFormField(DiskChoiceForm, "")
    custom_layout = RadioButtonField(radio_group, _("Custom storage layout"))

    cancel_label = _("Back")

    def __init__(self, model, initial):
        self.model = model
        super().__init__(initial=initial)
        self.in_signal = False
        connect_signal(
            self.guided_layout.widget, 'change', self._toggle_layout)
        connect_signal(
            self.custom_layout.widget, 'change', self._toggle_layout)
        self._toggle_layout(self.guided_layout.widget, self.guided_layout.value)

    def _toggle_layout(self, sender, new_value):
        if self.in_signal:
            return
        self.in_signal = True
        if sender is self.guided_layout.widget:
            guided_layout = new_value
        if sender is self.custom_layout.widget:
            guided_layout = not new_value

        # radio button behaviour
        self.guided_layout.value = guided_layout
        self.custom_layout.value = not guided_layout

        # grey-out guided_layout dependencies
        self.guided_layout.enabled = guided_layout
        #self.use_lvm.enabled = guided_layout
        self.in_signal = False


class GuidedDiskSelectionView(BaseView):

    title = _("Filesystem setup")

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller

        initial = {
            "guided_layout": True
            }

        self.form = GuidedForm(model=self.model, initial=initial)

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        super().__init__(self.form.as_screen(
            focus_buttons=False, excerpt=text, narrow_rows=True))

    def done(self, result):
        results=result.as_data()
        if results['custom_layout']:
            self.controller.manual()
        if results['guided_layout']:
            self.method = 'direct'
            if results['use_lvm']:
                self.method = 'lvm'
            self.choose_disk(results['guided_choice']['disk_choice'])

    def cancel(self, btn=None):
        self.controller.cancel()

    def choose_disk(self, disk):
        self.controller.reformat(disk)
        if self.method == "direct":
            result = {
                "size": disk.free_for_partitions,
                "fstype": "ext4",
                "mount": "/",
                }
            self.controller.partition_disk_handler(disk, None, result)
        elif self.method == 'lvm':
            if DeviceAction.MAKE_BOOT in disk.supported_actions:
                self.controller.make_boot_disk(disk)
            self.controller.create_partition(
                device=disk, spec=dict(
                    size=dehumanize_size('1G'),
                    fstype="ext4",
                    mount='/boot'
                    ))
            part = self.controller.create_partition(
                device=disk, spec=dict(
                    size=disk.free_for_partitions,
                    fstype=None,
                    ))
            spec = dict(name="ubuntu-vg", devices=set([part]))
            # create volume group on partition
            vg = self.controller.create_volgroup(spec)
            self.controller.create_logical_volume(
                vg=vg, spec=dict(
                    size=dehumanize_size("4G"),
                    name="ubuntu-lv",
                    fstype="ext4",
                    mount="/",
                    ))
        else:
            raise Exception("unknown guided method '{}'".format(self.method))
        self.controller.manual()
