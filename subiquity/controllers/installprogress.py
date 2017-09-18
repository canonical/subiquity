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
import random
import subprocess

from systemd import journal

from subiquitycore import utils
from subiquitycore.controller import BaseController

from subiquity.curtin import (CURTIN_CONFIGS,
                              CURTIN_INSTALL_LOG,
                              CURTIN_POSTINSTALL_LOG,
                              curtin_install_cmd,
                              curtin_write_network_config,
                              curtin_write_reporting_config)
from subiquity.models import InstallProgressModel
from subiquity.ui.views import ProgressView


log = logging.getLogger("subiquitycore.controller.installprogress")


class InstallState:
    NOT_STARTED = 0
    RUNNING_INSTALL = 1
    DONE_INSTALL = 2
    RUNNING_POSTINSTALL = 3
    DONE_POSTINSTALL = 4
    ERROR_INSTALL = -1
    ERROR_POSTINSTALL = -2


class InstallProgressController(BaseController):
    signals = [
        ('installprogress:curtin-install',     'curtin_start_install'),
        ('installprogress:wrote-install',      'curtin_wrote_install'),
        ('installprogress:wrote-postinstall',  'curtin_wrote_postinstall'),
        ('network-config-written',             'curtin_wrote_network_config'),
    ]

    def __init__(self, common):
        super().__init__(common)
        self.model = InstallProgressModel()
        self.progress_view = None
        self.install_state = InstallState.NOT_STARTED
        self.postinstall_written = False
        self.tail_proc = None
        self.journald_forwarder_proc = None
        self.curtin_event_stack = []

    def curtin_wrote_network_config(self, path):
        curtin_write_network_config(open(path).read())

    def curtin_wrote_install(self):
        pass

    def curtin_wrote_postinstall(self):
        self.postinstall_written = True
        if self.install_state == InstallState.DONE_INSTALL:
            self.curtin_start_postinstall()

    def curtin_error(self):
        log.debug('curtin_error')
        title = ('An error occurred during installation')
        self.ui.set_header(title, 'Please report this error in Launchpad')
        self.ui.set_footer("An error has occurred.", 100)
        if self.progress_view is not None:
            self.progress_view.set_status(('info_error', "An error has occurred"))
            self.progress_view.show_complete()
        else:
            self.default()

    def run_command_logged(self, cmd, logfile_location):
        with open(logfile_location, 'wb', buffering=0) as logfile:
            log.debug("running %s", cmd)
            cp = subprocess.run(
                cmd, stdout=logfile, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            log.debug("completed %s", cmd)
        return cp.returncode

    def curtin_event(self):
        if self.journal_reader.process() != journal.APPEND:
            return
        event = self.journal_reader.get_next()
        event_type = event.get("CURTIN_EVENT_TYPE")
        if random.randrange(1000) == 0 or len(event) > 0:
            log.debug("got curtin event from journald: %r", event)
        if event_type not in ['start', 'finish']:
            return
        if event_type == 'start':
            desc = event["MESSAGE"]
            self.curtin_event_stack.append(desc)
        if event_type == 'finish':
            if not self.curtin_event_stack:
                return
            self.curtin_event_stack.pop()
            if self.curtin_event_stack:
                desc = self.curtin_event_stack[-1]
            else:
                desc = ""
        self.ui.set_footer("Running install... %s" % (desc,))

    def start_event_listener(self):
        self.journal_reader = journal.Reader()
        self.journal_reader.seek_tail()
        self.journal_reader.add_match("SYSLOG_IDENTIFIER=curtin_event")
        self.journal_reader_handle = self.loop.watch_file(self.journal_reader.fileno(), self.curtin_event)

    def curtin_start_install(self):
        log.debug('Curtin Install: calling curtin with '
                  'storage/net/postinstall config')

        self.install_state = InstallState.RUNNING_INSTALL

        self.start_journald_forwarder()

        self.start_event_listener()

        curtin_write_reporting_config(self.reporting_url)

        if self.opts.dry_run:
            log.debug("Installprogress: this is a dry-run")
            curtin_cmd = [
                "python3", "scripts/replay-curtin-log.py",
                self.reporting_url, "examples/curtin-events-install.json",
                ]
        else:
            log.debug("Installprogress: this is the *REAL* thing")
            configs = [
                CURTIN_CONFIGS['storage'],
                CURTIN_CONFIGS['network'],
                CURTIN_CONFIGS['reporting'],
                ]
            curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin install cmd: {}'.format(curtin_cmd))
        self.run_in_bg(lambda: self.run_command_logged(curtin_cmd, CURTIN_INSTALL_LOG), self.curtin_install_completed)

    def curtin_install_completed(self, fut):
        returncode = fut.result()
        log.debug('curtin_install: returncode: {}'.format(returncode))
        self.stop_tail_proc()
        if returncode > 0:
            self.install_state = InstallState.ERROR_INSTALL
            self.curtin_error()
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
            self.start_tail_proc()
        if self.opts.dry_run:
            log.debug("Installprogress: this is a dry-run")
            curtin_cmd = [
                "python3", "scripts/replay-curtin-log.py",
                self.reporting_url, "examples/curtin-events-postinstall.json",
                ]
        else:
            log.debug("Installprogress: this is the *REAL* thing")
            configs = [
                CURTIN_CONFIGS['postinstall'],
                CURTIN_CONFIGS['preserved'],
                CURTIN_CONFIGS['reporting'],
                ]
            curtin_cmd = curtin_install_cmd(configs)

        log.debug('Curtin postinstall cmd: {}'.format(curtin_cmd))
        self.run_in_bg(lambda: self.run_command_logged(curtin_cmd, CURTIN_POSTINSTALL_LOG), self.curtin_postinstall_completed)

    def curtin_postinstall_completed(self, fut):
        returncode = fut.result()
        log.debug('curtin_postinstall: returncode: {}'.format(returncode))
        self.stop_tail_proc()
        if returncode > 0:
            self.install_state = InstallState.ERROR_POSTINSTALL
            self.curtin_error()
            return
        log.debug('After curtin postinstall OK')
        self.install_state = InstallState.DONE_POSTINSTALL
        self.ui.set_header("Installation complete!", "")
        self.ui.set_footer("", 100)
        self.progress_view.set_status("Finished install!")
        self.progress_view.show_complete()

    def update_log_tail(self):
        if self.tail_proc is None:
            return
        tail = self.tail_proc.stdout.read().decode('utf-8', 'replace')
        self.progress_view.add_log_tail(tail)

    def start_journald_forwarder(self):
        log.debug("starting curtin journald forwarder")
        if "SNAP" in os.environ:
            script = os.path.join(os.environ["SNAP"], 'usr/bin/curtin-journald-forwarder')
        else:
            script = './bin/curtin-journald-forwarder'
        self.journald_forwarder_proc = utils.run_command_start([script])
        self.reporting_url = self.journald_forwarder_proc.stdout.readline().decode('utf-8').strip()
        log.debug("curtin journald forwarder listening on %s", self.reporting_url)

    def start_tail_proc(self):
        if self.install_state == InstallState.ERROR_INSTALL:
            install_log = CURTIN_INSTALL_LOG
        elif self.install_state == InstallState.ERROR_POSTINSTALL:
            install_log = CURTIN_POSTINSTALL_LOG
        elif self.install_state < InstallState.RUNNING_POSTINSTALL:
            install_log = CURTIN_INSTALL_LOG
        else:
            install_log = CURTIN_POSTINSTALL_LOG
        self.progress_view.clear_log_tail()
        tail_cmd = ['tail', '-n', '1000', '-F', install_log]
        log.debug('tail cmd: {}'.format(" ".join(tail_cmd)))
        self.tail_proc = utils.run_command_start(tail_cmd)
        stdout_fileno = self.tail_proc.stdout.fileno()
        fcntl.fcntl(
            stdout_fileno, fcntl.F_SETFL,
            fcntl.fcntl(stdout_fileno, fcntl.F_GETFL) | os.O_NONBLOCK)
        self.tail_watcher_handle = self.loop.watch_file(stdout_fileno, self.update_log_tail)

    def stop_tail_proc(self):
        if self.tail_proc is not None:
            self.loop.remove_watch_file(self.tail_watcher_handle)
            self.tail_proc.terminate()
            self.tail_proc = None

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
        if self.install_state < 0:
            self.curtin_error()
            self.ui.set_body(self.progress_view)
            return
        if self.install_state < InstallState.RUNNING_POSTINSTALL:
            self.progress_view.set_status("Running install step")
        else:
            self.progress_view.set_status("Running postinstall step")
        self.ui.set_body(self.progress_view)

        self.start_tail_proc()
