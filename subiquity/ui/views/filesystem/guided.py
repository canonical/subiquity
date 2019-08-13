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
    Text,
    )

from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    ok_btn,
    )
from subiquitycore.ui.form import (
    Form,
    BooleanField,
    RadioButtonField,
    ChoiceField,
    )
from subiquitycore.ui.selector import (
    Option,
    )
from subiquitycore.ui.table import (
    ColSpec,
    TableListBox,
    TableRow,
    )
from subiquitycore.ui.utils import (
    button_pile,
    ClickableIcon,
    Color,
    CursorOverride,
    screen,
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


class GuidedForm(Form):

    radio_group = []
    guided_layout = RadioButtonField(radio_group, _("Use an entire disk"))
    # pad
    disk_choice = ChoiceField('', choices=["dummy"])
    # pad pad
    use_lvm = BooleanField(_("Set up this disk as an LVM group"))
    # pad pad pad even more
    custom_layout = RadioButtonField(radio_group, _("Custom storage layout"))

    cancel_label = _("Back")

    def __init__(self, initial):
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
        self.disk_choice.enabled = guided_layout
        self.use_lvm.enabled = guided_layout
        self.in_signal = False


class GuidedDiskSelectionView(BaseView):

    title = _("Filesystem setup")

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller

        initial = {
            "guided_layout": True
            }

        self.form = GuidedForm(initial=initial)

        disk_choices = [
            Option((disk.label, True, disk))
            for disk in self.model.all_disks()
        ]
        self.form.disk_choice.widget.options = disk_choices
        self.form.disk_choice.widget.value = disk_choices[0].value

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        super().__init__(self.form.as_screen(
            focus_buttons=True, excerpt=text, narrow_rows=True))

    def done(self, result):
        results=result.as_data()
        if results['custom_layout']:
            self.controller.manual()
        if results['guided_layout']:
            self.method = 'direct'
            if results['use_lvm']:
                self.method = 'lvm'
            self.choose_disk(results['disk_choice'])

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
