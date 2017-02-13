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

from subiquitycore.ui.utils import Padding
from subiquitycore.ui.container import ListBox
from subiquitycore.ui.form import Form
from subiquitycore.view import BaseView

from subiquity.ui.views.filesystem.add_partition import FSTypeField, MountField


log = logging.getLogger('subiquity.ui.filesystem.add_format')

class AddFormatForm(Form):

    def __init__(self, model):
        self.model = model
        super().__init__()

    fstype = FSTypeField("Format")
    mount = MountField("Mount")

    def validate_mount(self):
        mnts = self.model.get_mounts2()
        dev = mnts.get(self.mount.value)
        if dev is not None:
            return "%s is already mounted at %s"%(dev, self.mount.value)


class AddFormatView(BaseView):
    def __init__(self, model, controller, selected_disk):
        self.model = model
        self.controller = controller
        self.selected_disk = selected_disk
        self.disk_obj = self.model.get_disk(selected_disk)

        self.form = AddFormatForm(model)
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)
        connect_signal(self.form.fstype.widget, 'select', self.select_fstype)

        body = [
            Padding.line_break(""),
            self.form.as_rows(),
            Padding.line_break(""),
            Padding.fixed_10(self.form.buttons)
        ]
        format_box = Padding.center_50(ListBox(body))
        super().__init__(format_box)

    def select_fstype(self, sender, fs):
        self.form.mount.enabled = fs.is_mounted

    def cancel(self, button):
        self.controller.prev_view()

    def done(self, result):
        """ format spec

        {
          'format' Str(ext4|btrfs..,
          'mountpoint': Str
        }
        """
        fstype = self.form.fstype.value

        if fstype.is_mounted:
            mount = self.form.mount.value
        else:
            mount = None

        result = {
            "fstype": fstype.label,
            "mountpoint": mount,
        }

        log.debug("Add Format Result: {}".format(result))
        self.controller.add_disk_format_handler(self.disk_obj.devpath, result)
