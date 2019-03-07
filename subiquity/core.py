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
import os

from subiquitycore.core import Application

from subiquity.models.subiquity import SubiquityModel
from subiquity.snapd import (
    FakeSnapdConnection,
    SnapdConnection,
    )


log = logging.getLogger('subiquity.core')


class Subiquity(Application):

    snapd_socket_path = '/run/snapd.socket'

    from subiquity.palette import COLORS, STYLES, STYLES_MONO

    project = "subiquity"

    model_class = SubiquityModel

    controllers = [
            "Welcome",
            "Keyboard",
            "Installpath",
            "Network",
            "Proxy",
            "Mirror",
            "Filesystem",
            "Identity",
            "SSH",
            "SnapList",
            "InstallProgress",
    ]

    def __init__(self, ui, opts):
        super().__init__(ui, opts)
        self.common['ui'].progress_completion += 1
        if opts.snaps_from_examples:
            connection = FakeSnapdConnection(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(__file__)),
                    "examples", "snaps"))
        else:
            connection = SnapdConnection(self.root, self.snapd_socket_path)
        self.common['snapd_connection'] = connection
        signal = self.common['signal']
        signal.connect_signals([
            ('network-proxy-set', self._proxy_set),
            ('network-change', self._network_change),
            ])

    def _network_change(self):
        self.common['signal'].emit_signal('snapd-network-change')

    def _proxy_set(self):
        proxy_model = self.common['base_model'].proxy
        signal = self.common['signal']
        conn = self.common['snapd_connection']
        self.run_in_bg(
            lambda: conn.configure_proxy(proxy_model),
            lambda fut: (
                fut.result(), signal.emit_signal('snapd-network-change')),
            )
