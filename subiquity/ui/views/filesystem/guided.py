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

from urwid import (
    Text,
    )

from subiquitycore.ui.utils import Padding

from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    menu_btn,
    ok_btn,
    )
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.view import BaseView

from subiquity.models.filesystem import humanize_size


text = _("""The installer can guide you through partitioning a disk or, if \
you prefer, you can do it manually. If you choose guided partitioning you \
will still have a chance to review and modify the results.""")


class GuidedFilesystemView(BaseView):

    def __init__(self, model, controller):
        self.controller = controller
        guided = ok_btn(label=_("Guided"), on_press=self.guided)
        manual = ok_btn(label=_("Manual"), on_press=self.manual)
        back = back_btn(on_press=self.cancel)
        lb = ListBox([
            Padding.center_70(Text(text)),
            Padding.center_70(Text("")),
            Padding.fixed_10(guided),
            Padding.fixed_10(manual),
            Padding.fixed_10(back),
            ])
        super().__init__(lb)

    def manual(self, btn):
        self.controller.manual()

    def guided(self, btn):
        self.controller.guided()

    def cancel(self, btn=None):
        self.controller.cancel()


class GuidedDiskSelectionView(BaseView):

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        cancel = cancel_btn(on_press=self.cancel)
        disks = []
        for disk in self.model.all_disks():
            if disk.available:
                disk_btn = menu_btn(
                    "%-40s %s"%(disk.serial, humanize_size(disk.size).rjust(9)),
                    on_press=self.choose_disk, user_arg=disk)
                disks.append(disk_btn)
        lb = ListBox([
            Padding.center_70(Text(_("Choose the disk to install to:"))),
            Padding.center_70(Text("")),
            Padding.center_70(Pile(disks)),
            Padding.center_70(Text("")),
            Padding.fixed_10(cancel),
            ])
        super().__init__(lb)

    def cancel(self, btn=None):
        self.controller.default()

    def choose_disk(self, btn, disk):
        result = {
            "partnum": 1,
            "size": disk.free,
            "fstype": self.model.fs_by_name["ext4"],
            "mount": "/",
        }
        self.controller.partition_disk_handler(disk, None, result)
        self.controller.manual()
