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
    )

from subiquitycore.ui.form import (
    BooleanField,
    ChoiceField,
    Form,
    NO_CAPTION,
    NO_HELP,
    RadioButtonField,
    SubForm,
    SubFormField,
    )
from subiquitycore.ui.selector import Option
from subiquitycore.ui.table import (
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    rewrap,
    )
from subiquitycore.view import BaseView

from subiquity.models.filesystem import (
    DeviceAction,
    dehumanize_size,
    )

from .helpers import summarize_device

log = logging.getLogger("subiquity.ui.views.filesystem.guided")

text = _("""The installer can guide you through partitioning an entire disk
either directly or using LVM, or, if you prefer, you can do it manually.

If you choose to partition an entire disk you will still have a chance to
review and modify the results.""")


class GuidedChoiceForm(SubForm):

    disk = ChoiceField(caption=NO_CAPTION, help=NO_HELP, choices=["x"])
    use_lvm = BooleanField(_("Set up this disk as an LVM group"), help=NO_HELP)

    def __init__(self, parent):
        super().__init__(parent)
        options = []
        tables = []
        for disk in parent.model.all_disks():
            for obj, cells in summarize_device(disk):
                table = TablePile([TableRow(cells)])
                tables.append(table)
                options.append(Option((table, obj is disk, obj)))
        t0 = tables[0]
        for t in tables[1:]:
            t0.bind(t)
        self.disk.widget.options = options
        self.disk.widget.index = 0


class GuidedForm(Form):

    group = []

    guided = RadioButtonField(group, _("Use an entire disk"), help=NO_HELP)
    guided_choice = SubFormField(GuidedChoiceForm, "", help=NO_HELP)
    custom = RadioButtonField(group, _("Custom storage layout"), help=NO_HELP)

    cancel_label = _("Back")

    def __init__(self, model):
        self.model = model
        super().__init__()
        connect_signal(self.guided.widget, 'change', self._toggle_guided)

    def _toggle_guided(self, sender, new_value):
        self.guided_choice.enabled = new_value


class GuidedDiskSelectionView (BaseView):

    title = _("Filesystem setup")

    def __init__(self, controller):
        self.controller = controller
        self.form = GuidedForm(model=controller.model)

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        super().__init__(self.form.as_screen(
            focus_buttons=False, excerpt=rewrap(_(text))))

    def done(self, sender):
        results = sender.as_data()
        if results['custom']:
            self.controller.manual()
        else:  # results['guided']
            self.choose_disk(**results['guided_choice'])

    def cancel(self, btn=None):
        self.controller.cancel()

    def choose_disk(self, disk, use_lvm):
        self.controller.reformat(disk)
        if use_lvm:
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
            result = {
                "size": disk.free_for_partitions,
                "fstype": "ext4",
                "mount": "/",
                }
            self.controller.partition_disk_handler(disk, None, result)
        self.controller.manual()
