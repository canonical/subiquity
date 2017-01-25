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

import fcntl
import logging
import os
import subprocess

from subiquitycore import utils
from subiquitycore.controller import BaseController

from subiquity.curtin import (CURTIN_CONFIGS,
                              CURTIN_INSTALL_LOG,
                              CURTIN_POSTINSTALL_LOG,
                              curtin_install_cmd)
from subiquity.models import InstallProgressModel
from subiquity.ui.views import ProgressView


log = logging.getLogger("subiquitycore.controller.installprogress")


class InstallState:
    NOT_STARTED = 0
    RUNNING_INSTALL = 1
    DONE_INSTALL = 2
    RUNNING_POSTINSTALL = 3
    DONE_POSTINSTALL = 4
    ERROR = -1


class InstallProgressController(BaseController):
    signals = [
        ('installprogress:curtin-install',     'curtin_start_install'),
        ('installprogress:wrote-install',      'curtin_wrote_install'),
        ('installprogress:wrote-postinstall',  'curtin_wrote_postinstall'),
    ]

    def __init__(self, common):
        super().__init__(common)
        self.model = InstallProgressModel()
        self.progress_view = None
        self.install_state = InstallState.NOT_STARTED
        self.postinstall_written = False
        self.tail_proc = None

    def curtin_wrote_install(self):
        pass

    def curtin_wrote_postinstall(self):
        self.postinstall_written = True
        if self.install_state == InstallState.DONE_INSTALL:
            self.curtin_start_postinstall()

    @property
    def is_complete(self):
        log.debug('Checking is_complete: {} and {}'.format(
                  self.install_complete,
                  self.postinstall_complete))
        return (self.install_complete and self.postinstall_complete)

    def curtin_tail_install_log(self):
        if self.install_state < InstallState.RUNNING_POSTINSTALL:
            install_log = CURTIN_INSTALL_LOG
        else:
            install_log = CURTIN_POSTINSTALL_LOG
        if os.path.exists(install_log):
            tail_cmd = ['tail', '-n', '5', install_log]
            log.debug('tail cmd: {}'.format(" ".join(tail_cmd)))
            install_tail = subprocess.check_output(tail_cmd)
            return install_tail
        else:
            log.debug(('Install log not yet present:') +
                      '{}'.format(install_log))

        return ''

    def curtin_error(self):
        log.debug('curtin_error')
        title = ('An error occurred during installation')
        self.ui.set_header(title, 'Please report this error in Launchpad')
        self.progress_view.set_status("An error has occurred")
        self.ui.set_footer("An error has occurred.", 100)
        self.progress_view.show_complete()
        log.debug('curtin_error: refreshing final error screen')
        self.signal.emit_signal('refresh')

    def curtin_start_install(self):
        log.debug('Curtin Install: calling curtin with '
                  'storage/net/postinstall config')

        self.install_state = InstallState.RUNNING_INSTALL
        if self.opts.dry_run:
            log.debug("Installprogress: this is a dry-run")
            curtin_cmd = [
                "bash", "-c",
                "i=0;while [ $i -le 25 ];do i=$((i+1)); echo install line $i; sleep 1; done > %s 2>&1"%CURTIN_INSTALL_LOG]
        else:
            log.debug("Installprogress: this is the *REAL* thing")
            configs = [CURTIN_CONFIGS['storage']]
            curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin install cmd: {}'.format(curtin_cmd))
        self.run_in_bg(lambda: utils.run_command(curtin_cmd), self.curtin_install_completed)

    def curtin_install_completed(self, fut):
        result = fut.result()
        log.debug('curtin_install: result: {}'.format(result))
        if result['status'] > 0:
            msg = ("Problem with curtin "
                   "install: {}".format(result))
            log.error(msg)
            self.install_state = InstallState.ERROR
            return
        self.install_state = InstallState.DONE_INSTALL
        log.debug('After curtin install OK')
        if self.postinstall_written:
            self.curtin_start_postinstall()

    def cancel(self):
        pass

    def curtin_start_postinstall(self):
        log.debug('Curtin Post Install: calling curtin '
                  'with postinstall config')

        if not self.postinstall_written:
            log.error('Attempting to spawn curtin install without a config')
            raise Exception('AIEEE!')

        self.install_state = InstallState.RUNNING_POSTINSTALL
        if self.progress_view is not None:
            self.progress_view.clear_log_tail()
            self.progress_view.set_status("Running postinstall step")
            if self.tail_proc is not None:
                self.loop.remove_watch_file(self.tail_watcher_handle)
                self.tail_proc.terminate()
                self.tail_proc = None
        if self.opts.dry_run:
            log.debug("Installprogress: this is a dry-run")
            curtin_cmd = [
                "bash", "-c",
                "i=0;while [ $i -le 10 ];do i=$((i+1)); echo postinstall line $i; sleep 1; done > %s 2>&1"%CURTIN_POSTINSTALL_LOG]
        else:
            log.debug("Installprogress: this is the *REAL* thing")
            configs = [
                CURTIN_CONFIGS['postinstall'],
                CURTIN_CONFIGS['preserved'],
            ]
            curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin postinstall cmd: {}'.format(curtin_cmd))
        self.run_in_bg(lambda: utils.run_command(curtin_cmd), self.curtin_postinstall_completed)

    def curtin_postinstall_completed(self, fut):
        result = fut.result()
        if result['status'] > 0:
            msg = ("Problem with curtin "
                   "post-install: {}".format(result))
            log.error(msg)
            self.install_state = InstallState.ERROR
            return
        log.debug('After curtin postinstall OK')
        self.install_state = InstallState.DONE_POSTINSTALL

    def update_log_tail(self):
        if self.tail_proc is None:
            return
        tail = self.tail_proc.stdout.read().decode('utf-8', 'replace')
        self.progress_view.add_log_tail(tail)

    def maybe_start_tail_proc(self):
        if self.install_state < InstallState.RUNNING_POSTINSTALL:
            install_log = CURTIN_INSTALL_LOG
        else:
            install_log = CURTIN_POSTINSTALL_LOG
        if os.path.exists(install_log):
            self.progress_view.clear_log_tail()
            tail_cmd = ['tail', '-n', '1000', '-f', install_log]
            log.debug('tail cmd: {}'.format(" ".join(tail_cmd)))
            self.tail_proc = utils.run_command_start(tail_cmd)
            stdout_fileno = self.tail_proc.stdout.fileno()
            fcntl.fcntl(
                stdout_fileno, fcntl.F_SETFL,
                fcntl.fcntl(stdout_fileno, fcntl.F_GETFL) | os.O_NONBLOCK)
            self.tail_watcher_handle = self.loop.watch_file(stdout_fileno, self.update_log_tail)
        else:
            log.debug(('Install log not yet present:') +
                      '{}'.format(install_log))

    def progress_indicator(self, *args, **kwargs):
        if self.install_state == InstallState.ERROR:
            log.debug('progress_indicator: error detected')
            self.curtin_error()
        elif self.install_state == InstallState.DONE_POSTINSTALL:
            log.debug('progress_indicator: complete!')
            self.ui.set_footer("", 100)
            self.progress_view.set_status("Finished install!")
            self.progress_view.show_complete()
        elif self.tail_proc is None:
            self.maybe_start_tail_proc()
            self.loop.set_alarm_in(0.3, self.progress_indicator)
        else:
            self.loop.set_alarm_in(0.3, self.progress_indicator)

    def reboot(self):
        if self.opts.dry_run:
            log.debug('dry-run enabled, skipping reboot, quiting instead')
            self.signal.emit_signal('quit')
        else:
            utils.run_command(["/sbin/reboot"])

    def quit(self):
        if not self.opts.dry_run:
            utils.disable_subiquity()
        self.signal.emit_signal('quit')

    def default(self):
        log.debug('show_progress called')
        title = ("Installing system")
        excerpt = ("Please wait for the installation to finish.")
        footer = ("Thank you for using Ubuntu!")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 90)
        self.progress_view = ProgressView(self.model, self)
        if self.install_state < InstallState.RUNNING_POSTINSTALL:
            self.progress_view.set_status("Running install step")
        else:
            self.progress_view.set_status("Running postinstall step")
        self.ui.set_body(self.progress_view)

        self.progress_indicator()

        self.ui.set_footer(footer, 90)
