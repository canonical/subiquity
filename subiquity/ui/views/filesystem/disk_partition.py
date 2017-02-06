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
    def __init__(self, model, controller, selected_disk):
        self.model = model
        self.controller = controller
        self.selected_disk = selected_disk
        self.disk_obj = self.model.get_disk(self.selected_disk)

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
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def _build_model_inputs(self):
        partitioned_disks = []

        for mnt, size, fstype, path in self.disk_obj.get_fs_table():
            mnt = Text(mnt)
            size = Text("{}".format(_humanize_size(size)))
            fstype = Text(fstype) if fstype else '-'
            path = Text(path) if path else '-'
            partition_column = Columns([
                (15, path),
                size,
                fstype,
                mnt
            ], 4)
            partitioned_disks.append(partition_column)
        free_space = _humanize_size(self.disk_obj.freespace)
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
                on_press=self.show_disk_info
            ), focus_map='menu_button focus')

    def create_swap_w(self):
        """ Handles presenting an enabled create swap on
        entire device button if no partition exists, otherwise
        it is disabled.
        """
        text = ("Format or create swap on entire "
                "device (unusual, advanced)")
        if len(self.disk_obj.partitions) == 0 and \
           self.disk_obj.available:
            return Color.menu_button(menu_btn(label=text,
                                              on_press=self.create_swap),
                                     focus_map='menu_button focus')

    def add_partition_w(self):
        """ Handles presenting the add partition widget button
        depending on if partitions exist already or not.
        """
        text = "Add first GPT partition"
        if len(self.disk_obj.partitions) > 0:
            text = "Add partition (max size {})".format(
                _humanize_size(self.disk_obj.freespace))

        if self.disk_obj.available and \
           self.disk_obj.blocktype not in self.model.no_partition_blocktypes:
            return Color.menu_button(menu_btn(label=text,
                                              on_press=self.add_partition),
                                     focus_map='menu_button focus')

    def show_disk_info(self, result):
        self.controller.show_disk_information(self.selected_disk)

    def add_partition(self, result):
        log.debug('add_partition: result={}'.format(result))
        self.controller.add_disk_partition(self.selected_disk)

    def create_swap(self, result):
        log.debug('create_swap: result={}'.format(result))
        self.controller.create_swap_entire_device(self.selected_disk)

    def done(self, result):
        ''' Return to FilesystemView '''
        self.controller.prev_view()

    def cancel(self, button):
        self.controller.prev_view()
