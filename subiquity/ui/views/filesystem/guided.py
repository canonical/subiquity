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
    PasswordField,
    )
from subiquity.ui.views.identity import (
    setup_password_validation,
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
either directly or using LVM, or, if you prefer, you can do it manually.

If you choose to partition an entire disk you will still have a chance to \
review and modify the results.""")


class GuidedFilesystemView(BaseView):

    title = _("Filesystem setup")
    footer = _("Choose guided or manual partitioning")

    def __init__(self, controller):
        self.controller = controller
        direct = ok_btn(
            _("Use An Entire Disk"), on_press=self.guided, user_arg="direct")
        lvm = ok_btn(
            _("Use An Entire Disk And Set Up LVM"), on_press=self.guided,
            user_arg="lvm")
        luks = ok_btn(
            _("Use An Entire Disk And Set Up LUKS encrypted LVM"),
            on_press=self.guided_crypt, user_arg="luks")
        manual = ok_btn(_("Manual"), on_press=self.manual)
        back = back_btn(_("Back"), on_press=self.cancel)
        super().__init__(screen(
            rows=[button_pile([direct, lvm, luks, manual, back]), Text("")],
            buttons=None,
            focus_buttons=False,
            excerpt=text))

    def manual(self, btn):
        self.controller.manual()

    def guided(self, btn, method):
        self.controller.guided(method)

    def guided_crypt(self, btn, method):
        self.controller.guided_crypt(method)

    def cancel(self, btn=None):
        self.controller.cancel()


excerpts = {
    'direct': _("""The selected guided partitioning scheme creates the \
required bootloader partition on the chosen disk and then creates a single \
partition covering the rest of the disk, formatted as ext4 and mounted at '/'.\
"""),

    'lvm': _("""The LVM guided partitioning scheme creates three \
partitions on the selected disk: one as required by the bootloader, one \
for '/boot', and one covering the rest of the disk.

A LVM volume group is created containing the large partition. A \
4 gigabyte logical volume is created for the root filesystem. \
It can easily be enlarged with standard LVM command line tools."""),
    'luks': _("""The LUKS encrypted LVM guided partitioning scheme creates three \
partitions on the selected disk: one as required by the bootloader, one \
for '/boot', and one covering the rest of the disk.

A LUKS encrypted LVM volume group is created containing the large partition. \
A 4 gigabyte logical volume is created for the root filesystem. \
It can easily be enlarged with standard LVM command line tools."""),
}


def _wrap_button_row(row):
    return CursorOverride(Color.done_button(row), 2)


loss_warning = _("""Warning: If you lose this security key, all data will be lost. If \
you need to, write down your key and keep it in a safe place \
elsewhere.""")


class GuidedPasswordForm(Form):

    def __init__(self):
        super().__init__()
        setup_password_validation(self, _("Security key"))

    cancel_label = _("Back")
    password = PasswordField(_("Choose a security key:"))
    confirm_password = PasswordField(_("Confirm the security key:"),
                                     help=loss_warning)

    def validate_password(self):
        if len(self.password.value) < 1:
            return _("Security key must be set")

    def validate_confirm_passwor(self):
        if self.password.value != self.confirm_password.value:
            return _("Security keys do not match")


class GuidedPasswordView(BaseView):
    title = _("Choose a security key")
    footer = _("")
    excerpt = _("""Disk encryption protects your files in case you lose your \
computer. It requires you to enter a security key each time the \
computer starts up.

Any files outside of Ubuntu will not be encrypted.""")

    def __init__(self, model, controller, method):
        self.model = model
        self.controller = controller
        self.method = method
        self.form = GuidedPasswordForm()

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        super().__init__(self.form.as_screen(excerpt=_(self.excerpt),
                                             focus_buttons=False))

    def cancel(self, button=None):
        self.controller.guided_passphrase = ''
        self.controller.default()

    def done(self, result):
        self.controller.guided_passphrase = result.password.value
        self.controller.guided(self.method)


class GuidedDiskSelectionView(BaseView):

    title = _("Filesystem setup")
    footer = (_("Choose the installation target"))

    def __init__(self, model, controller, method):
        self.model = model
        self.controller = controller
        self.method = method
        cancel = cancel_btn(_("Cancel"), on_press=self.cancel)
        rows = []
        for disk in self.model.all_disks():
            for obj, cells in summarize_device(disk):
                wrap = Color.info_minor
                if obj is disk:
                    start, end = '[', ']'
                    arrow = '\N{BLACK RIGHT-POINTING SMALL TRIANGLE}'
                    if disk.size >= dehumanize_size("6G"):
                        arrow = ClickableIcon(arrow)
                        connect_signal(
                            arrow, 'click', self.choose_disk, disk)
                        wrap = _wrap_button_row
                else:
                    start, arrow, end = '', '', ''
                if isinstance(arrow, str):
                    arrow = Text(arrow)
                rows.append(wrap(TableRow(
                    [Text(start)] + cells + [arrow, Text(end)])))
            rows.append(TableRow([Text("")]))
        super().__init__(screen(
            TableListBox(rows[:-1], spacing=2, colspecs={
                0: ColSpec(rpad=1),
                2: ColSpec(can_shrink=True),
                4: ColSpec(min_width=9),
                5: ColSpec(rpad=1),
                }, align='center'),
            button_pile([cancel]),
            focus_buttons=False,
            excerpt=(
                excerpts[method]
                + "\n\n"
                + _("Choose the disk to install to:"))))

    def cancel(self, btn=None):
        if self.method == "luks":
            self.controller.guided_crypt(self.method)
        else:
            self.controller.default()

    def choose_disk(self, btn, disk):
        self.controller.reformat(disk)
        if self.method == "direct":
            result = {
                "size": disk.free_for_partitions,
                "fstype": "ext4",
                "mount": "/",
                }
            self.controller.partition_disk_handler(disk, None, result)
        elif self.method in ['lvm', 'luks']:
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
            if self.method == 'luks':
                spec['password'] = self.controller.guided_passphrase
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
