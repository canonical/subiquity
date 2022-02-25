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

from subiquitycore.ui.buttons import done_btn
from subiquitycore.ui.utils import button_pile
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import ColSpec, TablePile, TableRow

from subiquity.common.filesystem import labels


log = logging.getLogger('subiquity.ui.views.filesystem.disk_info')


labels_keys = [
    ('Path:', 'devname'),
    ('Multipath:', 'multipath'),
    ('Vendor:', 'vendor'),
    ('Model:', 'model'),
    ('SerialNo:', 'serial'),
    ('WWN:', 'wwn'),
    ('Size:', 'size'),
    ('Bus:', 'bus'),
    ('Rotational:', 'rotational'),
    ('Path:', 'devpath'),
]


class DiskInfoStretchy(Stretchy):
    def __init__(self, parent, disk):
        self.parent = parent
        dinfo = disk.info_for_display()
        rows = []
        for label, key in labels_keys:
            v = str(dinfo[key])
            rows.append(TableRow([Text(label, align='right'), Text(v)]))
        widgets = [
            TablePile(rows, colspecs={1: ColSpec(can_shrink=True)}),
            Text(""),
            button_pile([done_btn(_("Close"), on_press=self.close)]),
            ]
        title = _("Info for {device}").format(device=labels.label(disk))
        super().__init__(title, widgets, 0, 2)

    def close(self, button=None):
        self.parent.remove_overlay()
