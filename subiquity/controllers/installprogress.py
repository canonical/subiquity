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
        self.progress_output_w = ProgressOutput(
            self.signal,
            "Waiting...")

    def exit_cb(self, ret):
        log.debug("Exit: {}".format(ret))

    @coroutine
    def run_curtin(self):
        try:
            yield utils.run_command_async(
                "/usr/local/bin/curtin_wrap.sh",
                self.install_progress_status)
        except Exception as e:
            # TODO: Implement an Error View/Controller for displaying
            # exceptions rather than kicking out of installer.
            log.error("Problem running curtin_wrap: {}".format(e))

    @coroutine
    def run_test_curtin(self):
        """ testing streaming output
        """
        self.install_progress_status("Starting run")
        yield utils.run_command_async(
            "cat /var/log/syslog",
            self.install_progress_status)
        log.debug("done")
        return

    def install_progress(self):
        title = ("Installing system")
        excerpt = ("Please wait for the installation "
                   "to finish before rebooting.")
        footer = ("Thank you for using Ubuntu!")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(ProgressView(self.signal, self.progress_output_w))
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
            self.install_progress_status("\n".join(banner))
            # XXX: Test routine to verify the callback streaming
            # self.run_test_curtin()
        else:
            log.debug("filesystem: this is the *real* thing")
            self.run_curtin()

    def install_progress_status(self, data):
        log.debug("Running status output: {}".format(data))
        self.progress_output_w.set_text(data)
        self.signal.emit_signal('refresh')
