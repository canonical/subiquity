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
from tornado.gen import coroutine
import subiquity.utils as utils
from subiquity.models import InstallProgressModel
from subiquity.ui.views import ProgressView, ProgressOutput
from subiquity.controller import ControllerPolicy

log = logging.getLogger("subiquity.controller.installprogress")


class InstallProgressController(ControllerPolicy):
    def __init__(self, ui, signal, opts):
        self.ui = ui
        self.signal = signal
        self.opts = opts
        self.model = InstallProgressModel()
        self.progress_output_w = ProgressOutput(self.signal, "Waiting...")

    def install_progress_status(self, data):
        self.progress_output_w.set_text(data)
        self.signal.emit_signal('refresh')

    @coroutine
    def curtin_dispatch(self):
        if self.opts.dry_run:
            log.debug("Install Progress: Curtin dispatch dry-run")
            yield utils.run_command_async("cat /var/log/syslog",
                                          self.install_progress_status)
        else:
            try:
                yield utils.run_command_async("/usr/local/bin/curtin_wrap.sh",
                                              self.install_progress_status)
            except:
                log.error("Problem with curtin dispatch run")
                raise Exception("Problem with curtin dispatch run")

    @coroutine
    def initial_install(self):
        if self.opts.dry_run:
            log.debug("Filesystem: this is a dry-run")
            yield utils.run_command_async("cat /var/log/syslog",
                                          log.debug)
        else:
            log.debug("filesystem: this is the *real* thing")
            yield utils.run_command_async(
                "/usr/local/bin/curtin_wrap.sh",
                log.debug)

    @coroutine
    def show_progress(self):
        title = ("Installing system")
        excerpt = ("Please wait for the installation "
                   "to finish before rebooting.")
        footer = ("Thank you for using Ubuntu!")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(ProgressView(self.signal, self.progress_output_w))

        if self.opts.dry_run:
            banner = [
                "**** DRY_RUN ****",
                "NOT calling:"
                "subprocess.check_call(/usr/local/bin/curtin_wrap.sh)"
                "",
                "",
                "Press (Q) to Quit."
            ]
            self.install_progress_status("\n".join(banner))
