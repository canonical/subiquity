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
from subiquity.curtin import (CURTIN_CONFIGS,
                              curtin_install_cmd,
                              curtin_write_postinst_config)

log = logging.getLogger("subiquity.controller.installprogress")


class InstallProgressController(ControllerPolicy):
    def __init__(self, common):
        super().__init__(common)
        self.model = InstallProgressModel()
        self.progress_output_w = ProgressOutput(self.signal, "Waiting...")

    def install_progress_status(self, data):
        self.progress_output_w.set_text(data)
        self.signal.emit_signal('refresh')

    def curtin_dispatch(self, postconfig):
        ''' one time curtin dispatch requires the use of
            the preserved storage config which allows executing
            in-target commands by remounting up the configured
            storage.
        '''
        write_fd = self.loop.watch_pipe(self.install_progress_status)

        log.debug('writing out postinst config')
        curtin_write_postinst_config(postconfig)
        configs = [CURTIN_CONFIGS['preserved'], CURTIN_CONFIGS['postinstall']]
        curtin_cmd = curtin_install_cmd(configs)
        log.debug('Curtin postinstall install cmd: {}'.format(curtin_cmd))
        self._curtin_dispatch(curtin_cmd)

    @coroutine
    def _curtin_dispatch(self, curtin_cmd):
        if self.opts.dry_run:
            log.debug("Install Progress: Curtin dispatch dry-run")
            yield utils.run_command_async(['cat', '/var/log/syslog'],
                                          write_fd)
        else:
            try:
                yield utils.run_command_async(curtin_cmd, write_fd)
            except:
                log.error("Problem with curtin dispatch run")
                raise Exception("Problem with curtin dispatch run")

        return

    def initial_install(self):
        log.debug('Initial Install: calling curtin with storage/net config')
        write_fd = self.loop.watch_pipe(self.install_progress_status)

        configs = [CURTIN_CONFIGS['network'], CURTIN_CONFIGS['storage']]
        curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin install cmd: {}'.format(curtin_cmd))
        self._initial_install(curtin_cmd)

    @coroutine
    def _initial_install(self, curtin_cmd):
        if self.opts.dry_run:
            log.debug("Filesystem: this is a dry-run")
            yield utils.run_command_async(['cat', '/var/log/syslog'],
                                          write_fd)
        else:
            log.debug("filesystem: this is the *real* thing")
            yield utils.run_command_async(curtin_cmd, write_fd)

        return

    @coroutine
    def show_progress(self):
        log.debug('show_progress called')
        title = ("Installing system")
        excerpt = ("Please wait for the installation "
                   "to finish before rebooting.")
        footer = ("Thank you for using Ubuntu!")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 90)
        self.ui.set_body(ProgressView(self.signal, self.progress_output_w))

        if self.opts.dry_run:
            banner = [
                "**** DRY_RUN ****",
                ""
                "",
                "",
                "",
                "Press (Q) to Quit."
            ]
            self.install_progress_status("\n".join(banner))
            self.ui.set_footer(footer, 100)
