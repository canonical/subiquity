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

from subiquitycore.ui.lists import SimpleList
from subiquitycore.ui.buttons import done_btn
from subiquitycore.ui.utils import button_pile, Padding
from subiquitycore.ui.stretchy import Stretchy


log = logging.getLogger('subiquity.ui.filesystem.disk_info')


class DiskInfoStretchy(Stretchy):
    def __init__(self, parent, disk):
        log.debug('DiskInfoView: {}'.format(disk))
        self.parent = parent
        dinfo = disk.info_for_display()
        template = """\
{devname}:\n
 Vendor: {vendor}
 Model: {model}
 SerialNo: {serial}
 Size: {humansize} ({size}B)
 Bus: {bus}
 Rotational: {rotational}
 Path: {devpath}"""
        result = template.format(**dinfo)
        widgets = [
            Text(result),
            Text(""),
            button_pile([done_btn(_("Done"), on_press=self.cancel)]),
            ]
        title = _("Info for {}").format(disk.label)
        super().__init__(title, widgets, 0, 0)

    def _build_buttons(self):
        return button_pile([done_btn(_("Done"), on_press=self.done)])

    def keypress(self, size, key):
        if key in ['tab', 'n', 'N', 'j', 'J']:
            log.debug('keypress: [{}]'.format(key))
            self.controller.show_disk_information_next(self.disk)
            return None
        if key in ['shift tab', 'p', 'P', 'k', 'K']:
            log.debug('keypress: [{}]'.format(key))
            self.controller.show_disk_information_prev(self.disk)
            return None

        return super().keypress(size, key)

    def done(self, result):
        ''' Return to FilesystemView '''
        self.controller.partition_disk(self.disk)

    def cancel(self, button=None):
        self.parent.remove_overlay()
