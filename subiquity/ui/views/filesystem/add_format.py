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
from urwid import connect_signal

from subiquitycore.ui.buttons import done_btn, cancel_btn
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.ui.interactive import Selector
from subiquitycore.view import BaseView

from subiquity.ui.mount import MountSelector
from subiquity.ui.views.filesystem.add_partition import _col, Toggleable, ErrorDecoration


log = logging.getLogger('subiquity.ui.filesystem.add_format')


class AddFormatView(BaseView):
    def __init__(self, model, controller, selected_disk):
        self.model = model
        self.controller = controller
        self.selected_disk = selected_disk
        self.disk_obj = self.model.get_disk(selected_disk)

        self.mountpoint = MountSelector(self.model)

        self.fstype = Selector(opts=self.model.supported_filesystems)
        connect_signal(self.fstype, 'select', self.select_fstype)

        self.buttons = self._build_buttons()
        body = [
            Padding.line_break(""),
            self._build_container(),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        format_box = Padding.center_50(ListBox(body))
        super().__init__(format_box)

    def _build_buttons(self):
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done, focus_map='button focus'),
            Color.button(cancel, focus_map='button focus')
        ]
        return Pile(buttons)

    def _validate_mount(self):
        mnts = self.model.get_mounts2()
        dev = mnts.get(self.mountpoint.value)
        if dev is not None:
            return "%s is already mounted at %s"%(dev, self.mountpoint.value)

    def _build_container(self):
        self.fstype_decorated = Color.string_input(self.fstype, focus_map='string_input focus')
        self.fstype_row = _col("Format", self.fstype_decorated)

        self.mountpoint_decorated = Toggleable(self.mountpoint, 'string_input')
        self.mountpoint_row = _col("Mount", self.mountpoint_decorated, validator=self._validate_mount)

        self.all_rows = [
            self.fstype_row,
            self.mountpoint_row,
        ]
        for row in self.all_rows:
            connect_signal(row, 'validated', self._validated)
        return Pile(self.all_rows)

    def _validated(self, sender):
        error = False
        for w in self.all_rows:
            if w.has_error():
                log.debug("%s has error", w)
                error = True
        if error:
            self.buttons[0].disable()
            self.buttons.focus_position = 1
        else:
            self.buttons[0].enable()

    def _enable_disable_mount(self, enabled):
        if enabled:
            self.mountpoint_decorated.enable()
            self.mountpoint_row.validate()
        else:
            self.mountpoint_decorated.disable()
            self.mountpoint_row.hide_error()

    def select_fstype(self, sender, fs):
        if fs.is_mounted != sender.value.is_mounted:
            self._enable_disable_mount(fs.is_mounted)

    def cancel(self, button):
        self.controller.prev_view()

    def done(self, result):
        """ format spec

        {
          'format' Str(ext4|btrfs..,
          'mountpoint': Str
        }
        """

        result = {
            "fstype": self.fstype.value.label,
            "mountpoint": self.mountpoint.value
        }

        if self.mountpoint.value is not None:
            # Validate mountpoint input
            try:
                self.model.valid_mount(result)
            except ValueError as e:
                log.exception('Invalid mount point')
                self.mountpoint.set_error('Error: {}'.format(str(e)))
                log.debug('Invalid mountpoint, try again')
                return

        log.debug("Add Format Result: {}".format(result))
        self.controller.add_disk_format_handler(self.disk_obj.devpath, result)
