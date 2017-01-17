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

from subiquitycore import utils
from subiquitycore.controller import BaseController

from subiquity.curtin import (CURTIN_CONFIGS,
                              CURTIN_INSTALL_LOG,
                              CURTIN_POSTINSTALL_LOG,
                              curtin_reboot,
                              curtin_install_cmd)
from subiquity.models import InstallProgressModel
from subiquity.ui.views import ProgressView


log = logging.getLogger("subiquitycore.controller.installprogress")


class InstallProgressController(BaseController):
    signals = [
        ('installprogress:curtin-install',     'curtin_start_install'),
        ('installprogress:curtin-postinstall', 'curtin_start_postinstall'),
        ('installprogress:wrote-install',      'curtin_wrote_install'),
        ('installprogress:wrote-postinstall',  'curtin_wrote_postinstall'),
        ('menu:installprogress:main',          'show_progress'),
        ("installprogress:curtin-reboot",      'reboot'),
    ]

    def __init__(self, common):
        super().__init__(common)
        self.model = InstallProgressModel()
        self.progress_view = None
        self.alarm = None
        self.install_log = CURTIN_INSTALL_LOG

        # state flags
        self.install_error = False
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

    def curtin_tail_install_log(self):
        if os.path.exists(self.install_log):
            tail_cmd = ['tail', '-n', '5', self.install_log]
            log.debug('tail cmd: {}'.format(" ".join(tail_cmd)))
            install_tail = subprocess.check_output(tail_cmd)
            return install_tail
        else:
            log.debug(('Install log not yet present:') +
                      '{}'.format(self.install_log))

        return ''

    def curtin_error(self):
        log.debug('curtin_error')
        # just the last ten lines
        errmsg = str(self.curtin_tail_install_log()[-800:])
        # Holy Unescaping Batman!
        errmsg = errmsg.replace("\\\'", "")
        errmsg = errmsg.replace("\'\'", "")
        errmsg = errmsg.replace("\\n\'\n", "\n")
        errmsg = errmsg.replace('\\n', '\n')
        log.error(errmsg)
        title = ('An error occurred during installation')
        self.ui.set_header(title, 'Please report this error in Launchpad')
        self.progress_view.text.set_text(errmsg)
        self.ui.set_footer("An error as occurred.", 100)
        self.progress_view.show_finished_button()
        log.debug('curtin_error: refreshing final error screen')
        self.signal.emit_signal('refresh')

    def curtin_start_install(self):
        log.debug('Curtin Install: calling curtin with '
                  'storage/net/postinstall config')

        if self.install_config is False:
            log.error('Attempting to spawn curtin install without a config')
            raise Exception('AIEEE!')

        self.install_spawned = True
        if self.opts.dry_run:
            log.debug("Installprogress: this is a dry-run")
            curtin_cmd = [
                "bash", "-c",
                "i=0;while [ $i -le 10 ];do i=$((i+1)); echo line $i; sleep 1; done > %s 2>&1"%self.install_log]
        else:
            log.debug("Installprogress: this is the *REAL* thing")
            configs = [CURTIN_CONFIGS['storage']]
            curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin install cmd: {}'.format(curtin_cmd))
        fut = utils.run_command_async(self.pool, curtin_cmd)
        fut.add_done_callback(self.curtin_install_completed)

    def curtin_install_completed(self, fut):
        result = fut.result()
        log.debug('curtin_install: result: {}'.format(result))
        if result['status'] > 0:
            msg = ("Problem with curtin "
                   "install: {}".format(result))
            log.error(msg)
            # stop the update and clear the screen
            self.install_error = True
            log.debug('curtin_install: clearing screen')
            self.progress_view.text.set_text('')
            self.signal.emit_signal('refresh')
            return
        log.debug('After curtin install OK')
        self.install_complete = True

    def cancel(self):
        pass

    def curtin_start_postinstall(self):
        log.debug('Curtin Post Install: calling curtin '
                  'with postinstall config')

        if self.postinstall_config is False:
            log.error('Attempting to spawn curtin install without a config')
            raise Exception('AIEEE!')

        self.postinstall_spawned = True
        self.install_log = CURTIN_POSTINSTALL_LOG
        if self.opts.dry_run:
            log.debug("Installprogress: this is a dry-run")
            curtin_cmd = [
                "bash", "-c",
                "i=0;while [ $i -le 10 ];do i=$((i+1)); echo line $i; sleep 1; done > %s 2>&1"%self.install_log]
        else:
            log.debug("Installprogress: this is the *REAL* thing")
            configs = [
                CURTIN_CONFIGS['postinstall'],
                CURTIN_CONFIGS['preserved'],
            ]
            curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin postinstall cmd: {}'.format(curtin_cmd))
        fut = utils.run_command_async(self.pool, curtin_cmd)
        fut.add_done_callback(self.curtin_postinstall_completed)

    def curtin_postinstall_completed(self, fut):
        result = fut.result()
        if result['status'] > 0:
            msg = ("Problem with curtin "
                   "post-install: {}".format(result))
            log.error(msg)
            # stop the update and clear the screen
            self.install_error = True
            log.debug('curtin_postinstall: clearing screen')
            self.progress_view.text.set_text('')
            self.signal.emit_signal('refresh')
            return
        log.debug('After curtin postinstall OK')
        self.postinstall_complete = True

    def progress_indicator(self, *args, **kwargs):
        log.debug('progress_indicator')
        if self.install_error:
            log.debug('progress_indicator: error detected')
            self.curtin_error()
            return
        if self.is_complete:
            log.debug('progress_indicator: complete!')
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
            log.debug('progress_indicator: looping')
            install_tail = self.curtin_tail_install_log()
            self.progress_view.text.set_text(install_tail)

        if not self.install_error:
            log.debug('progress_indicator: setting alarm')
            self.alarm = self.loop.set_alarm_in(0.3, self.progress_indicator)

    def reboot(self):
        if self.opts.dry_run:
            log.debug('dry-run enabled, skipping reboot, quiting instead')
            self.signal.emit_signal('quit')

        curtin_reboot()

    def show_progress(self):
        log.debug('show_progress called')
        title = ("Installing system")
        excerpt = ("Please wait for the installation to finish.")
        footer = ("Thank you for using Ubuntu!")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer, 90)
        self.progress_view = ProgressView(self.model, self.signal)
        self.ui.set_body(self.progress_view)

        self.alarm = self.loop.set_alarm_in(0.3, self.progress_indicator)

        self.ui.set_footer(footer, 90)

    default = show_progress
