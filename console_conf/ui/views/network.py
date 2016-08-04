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

""" Network Model

Provides network device listings and extended network information

"""

import logging
from urwid import (ListBox, Pile, BoxAdapter,
                   Text, Columns)
import yaml
from subiquitycore.ui.lists import SimpleList
from subiquitycore.ui.buttons import cancel_btn, menu_btn, done_btn
from subiquitycore.ui.utils import Padding, Color
from subiquitycore.view import BaseView


log = logging.getLogger('subiquitycore.views.network')


class NetworkView(BaseView):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
        self.items = []
        self.body = [
            Padding.center_79(self._build_model_inputs()),
            Padding.line_break(""),
##            Padding.center_79(self._build_additional_options()),
##            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons()),
        ]
        # FIXME determine which UX widget should have focus
        self.lb = ListBox(self.body)
        self.lb.set_focus(2)  # _build_buttons
        super().__init__(self.lb)

    def _build_buttons(self):
        cancel = Color.button(cancel_btn(on_press=self.cancel),
                              focus_map='button focus')
        done = Color.button(done_btn(on_press=self.done),
                            focus_map='button focus')
        self.default_focus = done

        buttons = [done, cancel]
        return Pile(buttons, focus_item=done)

    def _build_model_inputs(self):
        ifaces = [iface for (name, iface) in sorted(self.model.config.ethernets.items())]
        ifname_width = 8  # default padding

        col_1 = []
        for iface in ifaces:
            col_1.append(
                Color.info_major(
                    menu_btn(label=iface.name,
                             on_press=self.on_net_dev_press),
                    focus_map='button focus'))
            if iface.addresses:
                for addr in iface.addresses:
                    col_1.append(Text(""))  # space for address
            else:
                col_1.append(Text(""))  # space for <no addresses>
        col_1 = BoxAdapter(SimpleList(col_1),
                           height=len(col_1))

        col_2 = []
        for iface in ifaces:
            col_2.append(Text(iface.vendor))
            if iface.addresses:
                for addr in iface.addresses:
                    t = addr.with_prefixlen
                    if addr.version == 4:
                        if iface.dhcp4:
                            t += " (dhcp)"
                        else:
                            t += " (static)"
                    elif addr.version == 6:
                        if iface.dhcp6:
                            t += " (dhcp)"
                        else:
                            t += " (static)"
                            col_2.append(Text(t))
            else:
                col_2.append(Text("<no addresses>"))

        if len(col_2):
            col_2 = BoxAdapter(SimpleList(col_2, is_selectable=False),
                               height=len(col_2))
            ifname_width += len(max(ifaces, key=lambda x: len(x.name)).name)
            if ifname_width > 20:
                ifname_width = 20
        else:
            col_2 = Pile([Text("No network interfaces detected.")])

        return Columns([(ifname_width, col_1), col_2], 2)

    def done(self, result):
        self.signal.emit_signal('network:finish', self.model.config.render())

    def cancel(self, button):
        self.model.reset()
        self.signal.prev_signal()

    def on_net_dev_press(self, result):
        self.signal.emit_signal('menu:network:main:configure-interface', result.label)
