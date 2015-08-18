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
import subprocess
from subiquity.ui.views import ProgressView, ProgressOutput
from subiquity.controller import ControllerPolicy

log = logging.getLogger("subiquity.controller.installprogress")


class InstallProgressController(ControllerPolicy):
    def __init__(self, ui, signal):
        self.ui = ui
        self.signal = signal

    def install_progress(self):
        title = ("Installing system")
        excerpt = ("Please wait for the installation "
                   "to finish before rebooting.")
        footer = ("Thank you for using Ubuntu!")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        if self.opts.dry_run:
            log.debug("Filesystem: this is a dry-run")
            banner = [
                "**** DRY_RUN ****",
                "NOT calling:"
                "subprocess.check_call(/usr/local/bin/curtin_wrap.sh)"
                "",
                "",
                "Press (Q) to Quit."
            ]
            self.progress_output_w = ProgressOutput("\n".join(banner))
        else:
            log.debug("filesystem: this is the *real* thing")
            subprocess.Popen(["/usr/local/bin/curtin_wrap.sh"],
                             stdout=self.install_progress_fd,
                             bufsize=1,
                             universal_newlines=True)
            self.progress_output_w = ProgressOutput("Wait for it...\n\n")
        self.ui.set_body(ProgressView(self.signal, self.progress_output_w))

    def install_progress_status(self, data):
        self.progress_output_w.set_text(data)
