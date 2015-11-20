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
import subprocess
from tornado.gen import coroutine
import subiquity.utils as utils
from subiquity.models import InstallProgressModel
from subiquity.ui.views import ProgressView
from subiquity.controller import ControllerPolicy
from subiquity.curtin import (CURTIN_CONFIGS,
                              CURTIN_INSTALL_LOG,
                              CURTIN_POSTINSTALL_LOG,
                              curtin_reboot,
                              curtin_install_cmd)


log = logging.getLogger("subiquity.controller.installprogress")


class InstallProgressController(ControllerPolicy):
    def __init__(self, common):
        super().__init__(common)
        self.model = InstallProgressModel()
        self.progress_view = None
        self.alarm = None
        self.install_log = None

        # state flags
        self.install_config = False
        self.install_spawned = False
        self.install_complete = False
        self.postinstall_config = False
        self.postinstall_spawned = False
        self.postinstall_complete = False

    def curtin_wrote_install(self):
        self.install_config = True

    def curtin_wrote_postinstall(self):
        self.postinstall_config = True

    @property
    def is_complete(self):
        log.debug('Checking is_complete: {} and {}'.format(
                  self.install_complete,
                  self.postinstall_complete))
        return (self.install_complete and self.postinstall_complete)

    @coroutine
    def curtin_install(self):
        log.debug('Curtin Install: calling curtin with '
                  'storage/net/postinstall config')

        if self.install_config is False:
            log.error('Attempting to spawn curtin install without a config')
            raise Exception('AIEEE!')

        self.install_spawned = True
        self.install_log = CURTIN_INSTALL_LOG
        if self.opts.dry_run:
            log.debug("Installprogress: this is a dry-run")
            curtin_cmd = ["top", "-d", "0.5", "-n", "20", "-b", "-p",
                          str(os.getpid()), ">", self.install_log]
        else:
            log.debug("Installprogress: this is the *REAL* thing")
            configs = [CURTIN_CONFIGS['network'],
                       CURTIN_CONFIGS['storage']]
            curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin install cmd: {}'.format(curtin_cmd))
        result = yield utils.run_command_async(" ".join(curtin_cmd))
        if result['status'] > 0:
            msg = ("Problem with curtin "
                   "install: {}".format(result))
            log.error(msg)
            self.progress_view.text.set_text(msg)
            self.loop.remove_alarm(self.alarm)
        log.debug('After curtin install OK')
        self.install_complete = True

    @coroutine
    def curtin_postinstall(self):
        log.debug('Curtin Post Install: calling curtin '
                  'with postinstall config')

        if self.postinstall_config is False:
            log.error('Attempting to spawn curtin install without a config')
            raise Exception('AIEEE!')

        self.postinstall_spawned = True
        self.install_log = CURTIN_POSTINSTALL_LOG
        if self.opts.dry_run:
            log.debug("Installprogress: this is a dry-run")
            curtin_cmd = ["top", "-d", "0.5", "-n", "20", "-b", "-p",
                          str(os.getpid()), ">", self.install_log]
        else:
            log.debug("Installprogress: this is the *REAL* thing")
            configs = [
                CURTIN_CONFIGS['postinstall'],
                CURTIN_CONFIGS['preserved'],
            ]
            curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin postinstall cmd: {}'.format(curtin_cmd))
        result = yield utils.run_command_async(" ".join(curtin_cmd))
        if result['status'] > 0:
            msg = ("Problem with curtin "
                   "install: {}".format(result))
            log.error(msg)
            self.progress_view.text.set_text(msg)
            self.loop.remove_alarm(self.alarm)
        self.postinstall_complete = True

    def progress_indicator(self, *args, **kwargs):
        if self.is_complete:
            self.progress_view.text.set_text("Finished install!")
            self.ui.set_footer("", 100)
            self.progress_view.show_finished_button()
            self.loop.remove_alarm(self.alarm)
            return
        elif (self.postinstall_config and
              self.install_complete and
              not self.postinstall_spawned):
            # kick off postinstall
            self.signal.emit_signal('installprogress:curtin-postinstall')
        else:
            if os.path.exists(self.install_log):
                tail_cmd = ['tail', '-n', '10', self.install_log]
                log.debug('tail cmd: {}'.format(" ".join(tail_cmd)))
                install_tail = subprocess.check_output(tail_cmd)
                self.progress_view.text.set_text(install_tail)
            else:
                log.debug(('Install log not yet present:') +
                          '{}'.format(self.install_log))

        self.alarm = self.loop.set_alarm_in(0.3, self.progress_indicator)

    def reboot(self):
        if self.opts.dry_run:
            log.debug('dry-run enabled, skipping reboot, quiting instead')
            self.signal.emit_signal('quit')

        curtin_reboot()

    @coroutine
    def show_progress(self):
        log.debug('show_progress called')
        title = ("Installing system")
        excerpt = ("Please wait for the installation "
                   "to finish before rebooting.")
        footer = ("Thank you for using Ubuntu!")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 90)
        self.progress_view = ProgressView(self.model, self.signal)
        self.ui.set_body(self.progress_view)

        if self.opts.dry_run:
            banner = [
                "**** DRY_RUN ****",
                ""
                "",
                "",
                "",
                "Press (Control-x) to Quit."
            ]
            self.progress_view.text.set_text("\n".join(banner))

        self.alarm = self.loop.set_alarm_in(0.3, self.progress_indicator)

        self.ui.set_footer(footer, 90)
