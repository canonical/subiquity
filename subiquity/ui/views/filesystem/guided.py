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
    Text,
    )

from subiquitycore.ui.utils import button_pile, Color, Padding
from subiquitycore.ui.buttons import (
    back_btn,
    cancel_btn,
    forward_btn,
    ok_btn,
    )
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.view import BaseView

from subiquity.models.filesystem import humanize_size

log = logging.getLogger("subiquity.ui.views.filesystem.guided")


text = _("""The installer can guide you through partitioning an entire disk \
or, if you prefer, you can do it manually.

If you choose to partition an entire disk you will still have a chance to \
review and modify the results.""")


class GuidedFilesystemView(BaseView):

    title = _("Filesystem setup")
    footer = _("Choose guided or manual partitioning")

    def __init__(self, controller):
        self.controller = controller
        guided = ok_btn(_("Use An Entire Disk"), on_press=self.guided)
        manual = ok_btn(_("Manual"), on_press=self.manual)
        back = back_btn(_("Back"), on_press=self.cancel)
        lb = ListBox([
            Padding.center_70(Text("")),
            Padding.center_70(Text(_(text))),
            Padding.center_70(Text("")),
            button_pile([guided, manual, back]),
            ])
        super().__init__(lb)

    def manual(self, btn):
        self.controller.manual()

    def guided(self, btn):
        self.controller.guided()

    def cancel(self, btn=None):
        self.controller.cancel()


class GuidedDiskSelectionView(BaseView):

    title = _("Filesystem setup")
    footer = (_("Choose the installation target"))

    def __init__(self, model, controller):
        self.model = model
        self.controller = controller
        cancel = cancel_btn(_("Cancel"), on_press=self.cancel)
        disks = []
        for disk in self.model.all_disks():
            label = "%-42s %s" % (disk.label,
                                  humanize_size(disk.size).rjust(9))
            if disk.size >= model.lower_size_limit:
                disk_btn = forward_btn(label, on_press=self.choose_disk,
                                       user_arg=disk)
            else:
                disk_btn = Color.info_minor(Text("  "+label))
            disks.append(disk_btn)
        body = Pile([
            ('pack', Text("")),
            ('pack', Padding.center_70(
                        Text(_("Choose the disk to install to:")))),
            ('pack', Text("")),
            Padding.center_70(ListBox(disks)),
            ('pack', Text("")),
            ('pack', button_pile([cancel])),
            ('pack', Text("")),
            ])
        super().__init__(body)

    def cancel(self, btn=None):
        self.controller.default()

    def choose_disk(self, btn, disk):
        self.model.reset()
        result = {
            "size": disk.free,
            "fstype": self.model.fs_by_name["ext4"],
            "mount": "/",
        }
        self.controller.partition_disk_handler(disk, None, result)
        self.controller.manual()
