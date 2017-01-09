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
from urwid import ListBox, Pile, Text, Columns

from subiquitycore.ui.buttons import done_btn, cancel_btn
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.ui.interactive import Selector, MountEditor
from subiquitycore.view import BaseView


log = logging.getLogger('subiquity.ui.filesystem.add_format')


class AddFormatView(BaseView):
    def __init__(self, model, controller, selected_disk):
        self.model = model
        self.controller = controller
        self.selected_disk = selected_disk
        self.disk_obj = self.model.get_disk(selected_disk)

        self.mountpoint = MountEditor(caption="", edit_text="/")
        self.fstype = Selector(opts=self.model.supported_filesystems)
        body = [
            Padding.line_break(""),
            self._container(),
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

    def _container(self):
        total_items = [
            Columns(
                [
                    ("weight", 0.2, Text("Format", align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.fstype,
                                        focus_map="string_input focus"))
                ], dividechars=4
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Mount", align="right")),
                    ("weight", 0.3,
                     Color.string_input(self.mountpoint,
                                        focus_map="string_input focs"))
                ], dividechars=4
            )
        ]
        return Pile(total_items)

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
            "fstype": self.fstype.value,
            "mountpoint": self.mountpoint.value
        }

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
