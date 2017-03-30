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
from urwid import BoxAdapter, Text

from subiquitycore.ui.lists import SimpleList
from subiquitycore.ui.buttons import done_btn, cancel_btn, menu_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView

from subiquity.models.filesystem import _humanize_size


log = logging.getLogger('subiquity.ui.filesystem.disk_partition')


class DiskPartitionView(BaseView):
    def __init__(self, model, controller, disk):
        self.model = model
        self.controller = controller
        self.disk = disk

        self.body = [
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
            Padding.center_79(self._build_menu()),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons()),
        ]
        super().__init__(ListBox(self.body))

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done),
            Color.button(cancel)
        ]
        return Pile(buttons)

    def _build_model_inputs(self):
        partitioned_disks = []

        def format_volume(label, part):
            size = _humanize_size(part.size)
            if part.fs() is None:
                 fstype = '-'
                 mountpoint = '-'
            elif part.fs().mount() is None:
                fstype = part.fs().fstype
                mountpoint = '-'
            else:
                fstype = part.fs().fstype
                mountpoint = part.fs().mount().path
            return Columns([
                (15, Text(label)),
                Text(size),
                Text(fstype),
                Text(mountpoint),
            ], 4)
        if self.disk.fs() is not None:
            partitioned_disks.append(format_volume("entire disk", self.disk))
        else:
            for part in self.disk.partitions():
                partitioned_disks.append(format_volume("partition {}".format(part.number), part))
        if self.disk.free > 0:
            free_space = _humanize_size(self.disk.free)
            partitioned_disks.append(Columns([
                (15, Text("FREE SPACE")),
                Text(free_space),
                Text(""),
                Text("")
            ], 4))

        return BoxAdapter(SimpleList(partitioned_disks, is_selectable=False),
                          height=len(partitioned_disks))

    def _build_menu(self):
        """
        Builds the add partition menu with user visible
        changes to the button depending on if existing
        partitions exist or not.
        """
        menus = [
            self.add_partition_w(),
            self.create_swap_w(),
            self.show_disk_info_w(),
        ]
        return Pile([m for m in menus if m])

    def show_disk_info_w(self):
        """ Runs hdparm against device and displays its output
        """
        text = ("Show disk information")
        return Color.menu_button(
            menu_btn(
                label=text,
                on_press=self.show_disk_info))

    def create_swap_w(self):
        """ Handles presenting an enabled create swap on
        entire device button if no partition exists, otherwise
        it is disabled.
        """
        text = ("Format or create swap on entire "
                "device (unusual, advanced)")
        if len(self.disk.partitions()) == 0 and \
           self.disk.available:
            return Color.menu_button(
                menu_btn(label=text, on_press=self.format_entire))

    def add_partition_w(self):
        """ Handles presenting the add partition widget button
        depending on if partitions exist already or not.
        """
        if not self.disk.available:
            return None
        text = "Add first partition"
        if len(self.disk.partitions()) > 0:
            text = "Add partition (max size {})".format(
                _humanize_size(self.disk.free))

        return Color.menu_button(
            menu_btn(label=text, on_press=self.add_partition))

    def show_disk_info(self, result):
        self.controller.show_disk_information(self.disk)

    def add_partition(self, result):
        self.controller.add_disk_partition(self.disk)

    def format_entire(self, result):
        self.controller.format_entire(self.disk)

    def done(self, result):
        ''' Return to FilesystemView '''
        self.controller.prev_view()

    def cancel(self, button):
        self.controller.prev_view()
