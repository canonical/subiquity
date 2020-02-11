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
    PasswordField,
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


from .helpers import summarize_device

log = logging.getLogger("subiquity.ui.views.filesystem.guided")

text = _("""The installer can guide you through partitioning an entire disk
either directly or using LVM, or, if you prefer, you can do it manually.

If you choose to partition an entire disk you will still have a chance to
review and modify the results.""")


class LUKSOptionsForm(SubForm):

    password = PasswordField(_("Passphrase:"))
    confirm_password = PasswordField(_("Confirm passphrase:"))

    def validate_password(self):
        if len(self.password.value) < 1:
            return _("Password must be set")

    def validate_confirm_password(self):
        if self.password.value != self.confirm_password.value:
            return _("Passwords do not match")


class LVMOptionsForm(SubForm):

    def __init__(self, parent):
        super().__init__(parent)
        connect_signal(self.encrypt.widget, 'change', self._toggle)
        self.luks_options.enabled = self.encrypt.value

    def _toggle(self, sender, val):
        self.luks_options.enabled = val

    encrypt = BooleanField(_("Encrypt the LVM group with LUKS"), help=NO_HELP)
    luks_options = SubFormField(LUKSOptionsForm, "", help=NO_HELP)


class GuidedChoiceForm(SubForm):

    disk = ChoiceField(caption=NO_CAPTION, help=NO_HELP, choices=["x"])
    use_lvm = BooleanField(_("Set up this disk as an LVM group"), help=NO_HELP)
    lvm_options = SubFormField(LVMOptionsForm, "", help=NO_HELP)

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
        connect_signal(self.use_lvm.widget, 'change', self._toggle)
        self.lvm_options.enabled = self.use_lvm.value

    def _toggle(self, sender, val):
        self.lvm_options.enabled = val


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


HELP = _("""

The "Use an entire disk" option installs Ubuntu onto the selected disk,
replacing any partitions and data already there.

If the platform requires it, a bootloader partition is created on the disk.

If you choose to use LVM, two partitions are then created, one for /boot and
one covering the rest of the disk. A LVM volume group is created containing
the large partition. A 4 gigabyte logical volume is created for the root
filesystem. It can easily be enlarged with standard LVM command line tools.

If you do not choose to use LVM, a single partition is created covering the
rest of the disk which is then formatted as ext4 and mounted at /.

In either case, you will still have a chance to review and modify the results.

If you choose to use a custom storage layout, no changes are made to the disks
and you will have to, at a minimum, select a boot disk and mount a filesystem
at /.

""")


class GuidedDiskSelectionView (BaseView):

    title = _("Filesystem setup")

    def __init__(self, controller):
        self.controller = controller
        self.form = GuidedForm(model=controller.model)

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        super().__init__(self.form.as_screen(
            focus_buttons=False, excerpt=rewrap(_(text))))

    def local_help(self):
        return (_("Help on guided storage configuration"), rewrap(_(HELP)))

    def done(self, sender):
        results = sender.as_data()
        if results['guided']:
            disk = results['guided_choice']['disk']
            if results['guided_choice']['use_lvm']:
                self.controller.guided_lvm(
                    disk, results['guided_choice']['lvm_options'])
            else:
                self.controller.guided_direct(disk)
        self.controller.manual()

    def cancel(self, btn=None):
        self.controller.cancel()
