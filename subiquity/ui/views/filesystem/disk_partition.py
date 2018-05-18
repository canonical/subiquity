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

import logging
from urwid import Text

from subiquitycore.ui.buttons import done_btn, cancel_btn, menu_btn, other_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.utils import button_pile, Padding
from subiquitycore.view import BaseView

from subiquity.models.filesystem import humanize_size


log = logging.getLogger('subiquity.ui.filesystem.disk_partition')


class DiskPartitionView(BaseView):
    footer = (_("Partition the disk, or format the entire device "
              "without partitions"))

    def __init__(self, model, controller, disk):
        self.model = model
        self.controller = controller
        self.disk = disk
        self.title = _("Partition, format, and mount {}").format(disk.label)

        self.body = Pile([
            ('pack', Text("")),
            Padding.center_79(ListBox(
                self._build_model_inputs() + [
                Text(""),
                self.show_disk_info_w(),
                ])),
            ('pack', Text("")),
            ('pack', self._build_buttons()),
            ('pack', Text("")),
            ])
        super().__init__(self.body)

    def _build_buttons(self):
        cancel = cancel_btn(_("Cancel"), on_press=self.cancel)
        done = done_btn(_("Done"), on_press=self.done)
        return button_pile([done, cancel])

    def _build_model_inputs(self):
        partitioned_disks = []

        if self.disk.free > 0:
            if len(self.disk.partitions()) > 0:
                final_label = _("Add another partition")
            else:
                final_label = _("Add first partition")
            label_width = max(25, len(final_label) + 4)
        else:
            label_width = 25

        def format_volume(label, part):
            size = humanize_size(part.size)
            if part.fs() is None:
                 fstype = '-'
                 mountpoint = '-'
            elif part.fs().mount() is None:
                fstype = part.fs().fstype
                mountpoint = '-'
            else:
                fstype = part.fs().fstype
                mountpoint = part.fs().mount().path
            if part.type == 'disk':
                part_btn = menu_btn(label, on_press=self._click_disk)
            else:
                part_btn = menu_btn(label, on_press=self._click_part, user_arg=part)
            return Columns([
                (label_width, part_btn),
                (9, Text(size, align="right")),
                Text(fstype),
                Text(mountpoint),
            ], 2)
        if self.disk.fs() is not None:
            partitioned_disks.append(format_volume(_("entire disk"), self.disk))
        else:
            for part in self.disk.partitions():
                partitioned_disks.append(format_volume(_("Partition {}").format(part._number), part))
        if self.disk.free > 0:
            free_space = humanize_size(self.disk.free)
            add_btn = menu_btn(final_label, on_press=self.add_partition)
            partitioned_disks.append(Columns([
                (label_width, add_btn),
                (9, Text(free_space, align="right")),
                Text(_("free space")),
            ], 2))
        if self.model.bootable():
            for p in self.disk.partitions():
                if p.flag in ('bios_grub', 'boot'):
                    break
            else:
                partitioned_disks.append(Text(""))
                partitioned_disks.append(
                    button_pile([other_btn(label=_("Select as boot disk"), on_press=self.make_boot_disk)]))
        if len(self.disk.partitions()) == 0 and \
           self.disk.available:
            text = _("Format or create swap on entire device (unusual, advanced)")
            partitioned_disks.append(Text(""))
            partitioned_disks.append(
                menu_btn(label=text, on_press=self.format_entire))

        return partitioned_disks

    def _click_part(self, sender, part):
        self.controller.edit_partition(self.disk, part)

    def _click_disk(self, sender):
        self.controller.format_entire(self.disk)

    def show_disk_info_w(self):
        """ Runs hdparm against device and displays its output
        """
        text = _("Show disk information")
        return menu_btn(
                label=text,
                on_press=self.show_disk_info)

    def show_disk_info(self, result):
        self.controller.show_disk_information(self.disk)

    def add_partition(self, result):
        self.controller.add_disk_partition(self.disk)

    def format_entire(self, result):
        self.controller.format_entire(self.disk)

    def make_boot_disk(self, sender):
        self.controller.make_boot_disk(self.disk)

    def done(self, result):
        ''' Return to FilesystemView '''
        self.controller.manual()

    def cancel(self, button=None):
        self.controller.manual()
