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
    connect_signal,
    Text,
    )

from subiquitycore.ui.utils import Padding, Color

from subiquitycore.ui.buttons import (
    menu_btn,
    PlainButton,
    )
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.view import BaseView

from subiquity.models.filesystem import humanize_size


text = """The installer can guide you through partitioning a disk or, if \
you prefer, you can do it manually. If you choose guided partitioning you \
will still have a chance to review and modify the results."""


class GuidedFilesystemView(BaseView):

    def __init__(self, model, controller):
        self.controller = controller
        guided = PlainButton(label="Guided")
        connect_signal(guided, 'click', self.guided)
        manual = PlainButton(label="Manual")
        connect_signal(manual, 'click', self.manual)
        lb = ListBox([
            Padding.center_70(Text(text)),
            Padding.center_70(Text("")),
            Padding.fixed_10(Color.button(guided)),
            Padding.fixed_10(Color.button(manual))])
        super().__init__(lb)

    def manual(self, btn):
        self.controller.manual()

    def guided(self, btn):
        self.controller.guided()

class GuidedDiskSelectionView(BaseView):

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        cancel = PlainButton(label="Cancel")
        connect_signal(cancel, 'click', self.cancel)
        disks = []
        for disk in self.model.all_disks():
            if disk.available:
                disk_btn = menu_btn("%-40s %s"%(disk.serial, humanize_size(disk.size).rjust(9)))
                connect_signal(disk_btn, 'click', self.choose_disk, disk)
                disks.append(Color.menu_button(disk_btn))
        lb = ListBox([
            Padding.center_70(Text("Choose the disk to install to:")),
            Padding.center_70(Text("")),
            Padding.center_70(Pile(disks)),
            Padding.center_70(Text("")),
            Padding.fixed_10(Color.button(cancel))])
        super().__init__(lb)

    def cancel(self, btn):
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
