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
from subiquitycore.ui.container import Pile
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView


log = logging.getLogger('subiquity.ui.filesystem.disk_info')


class DiskInfoView(BaseView):
    def __init__(self, model, controller, selected_device, hdinfo):
        log.debug('DiskInfoView: {}'.format(selected_device))
        self.model = model
        self.controller = controller
        self.selected_device = selected_device
        hdinfo = hdinfo.split("\n")
        body = []
        for h in hdinfo:
            body.append(Text(h))
        body.append(Padding.fixed_10(self._build_buttons()))
        super().__init__(Padding.center_79(SimpleList(body)))

    def _build_buttons(self):
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done),
        ]
        return Pile(buttons)

    def keypress(self, size, key):
        if key in ['tab', 'n', 'N', 'j', 'J']:
            log.debug('keypress: [{}]'.format(key))
            self.controller.show_disk_information_next(self.selected_device)
            return None
        if key in ['shift tab', 'p', 'P', 'k', 'K']:
            log.debug('keypress: [{}]'.format(key))
            self.controller.show_disk_information_prev(self.selected_device)
            return None

        return super().keypress(size, key)

    def done(self, result):
        ''' Return to FilesystemView '''
        self.controller.prev_view()

    def cancel(self, button):
        self.controller.prev_view()
