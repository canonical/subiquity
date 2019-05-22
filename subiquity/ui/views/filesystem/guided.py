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
from subiquitycore.ui.table import (
    ColSpec,
    TableListBox,
    TableRow,
    )
from subiquitycore.ui.utils import (
    button_pile,
    ClickableIcon,
    Color,
    screen,
    )
from subiquitycore.view import BaseView

from subiquity.models.filesystem import (
    DeviceAction,
    dehumanize_size,
    humanize_size,
    )
from .delete import summarize_partitions

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
        manual = ok_btn(_("Manual"), on_press=self.manual)
        back = back_btn(_("Back"), on_press=self.cancel)
        super().__init__(screen(
            rows=[button_pile([direct, lvm, manual, back]), Text("")],
            buttons=None,
            focus_buttons=False,
            excerpt=text))

    def manual(self, btn):
        self.controller.manual()

    def guided(self, btn, method):
        self.controller.guided(method)

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
}


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
            if disk.size >= dehumanize_size("6G"):
                disk_btn = ClickableIcon(disk.label)
                connect_signal(
                    disk_btn, 'click', self.choose_disk, disk.path)
                attr = Color.done_button
            else:
                disk_btn = Text("  "+disk.label)
                attr = Color.info_minor
            rows.append(attr(TableRow([
                Text('['),
                disk_btn,
                Text(humanize_size(disk.size), align='right'),
                Text('\N{BLACK RIGHT-POINTING SMALL TRIANGLE}'),
                Text(']'),
                ])))
            if disk.used > 0:
                if len(disk.partitions()) > 0:
                    summary = summarize_partitions(disk)
                else:
                    summary = Text(", ".join(disk.usage_labels()))
                rows.append(TableRow([
                    Text(""), (2, Color.info_minor(summary))]))
        super().__init__(screen(
            TableListBox(rows, spacing=1, colspecs={
                1: ColSpec(can_shrink=True, min_width=20, rpad=2),
                2: ColSpec(min_width=9),
                }, align='center'),
            button_pile([cancel]),
            focus_buttons=False,
            excerpt=(
                excerpts[method]
                + "\n\n"
                + _("Choose the disk to install to:"))))

    def cancel(self, btn=None):
        self.controller.default()

    def choose_disk(self, btn, disk_path):
        self.model.reset()
        disk = self.model.disk_by_path(disk_path)
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
            vg = self.controller.create_volgroup(
                spec=dict(
                    name="ubuntu-vg",
                    devices=set([part]),
                    ))
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
