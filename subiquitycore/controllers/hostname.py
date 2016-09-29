# Copyright 2016 Canonical, Ltd.
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

from subiquitycore.controller import BaseController
from subiquitycore.ui.views import HostnameView
from subiquitycore.utils import run_command

log = logging.getLogger('subiquitycore.controllers.hostname')


class HostnameController(BaseController):

    def default(self):
        title = "Hostname configuration"
        excerpt = "Enter the hostname to use for the device"
        self.ui.set_header(title, excerpt)
        view = HostnameView(self)
        self.ui.set_body(view)

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def done(self, hostname):
        if not self.opts.dry_run:
             # Call hostname to set the name first, to give it a chance to object to an invalid name.
             cmd = ["hostname", self.hostname.value]
             result = run_command(cmd)
             log.debug('ran %s with result %s'%(cmd, result))
             if result['status'] != 0:
                 self.ui.frame.body.error.set_text("Setting hostname failed: %s" % (result['err'],))
                 return
             with open("/etc/hostname", "w") as hn:
                 hn.write(self.hostname.value + "\n")
        self.signal.emit_signal('next-screen')

