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

import datetime
import logging
import os
import subprocess
import sys
import platform
import time
import traceback

import urwid
import yaml

from systemd import journal

from subiquitycore import utils
from subiquitycore.controller import BaseController
from subiquitycore.tasksequence import (
    BackgroundTask,
    TaskSequence,
    TaskWatcher,
    )

from subiquity.ui.views.installprogress import ProgressView


log = logging.getLogger("subiquitycore.controller.installprogress")


class InstallState:
    NOT_STARTED = 0
    RUNNING = 1
    DONE = 2
    ERROR = -1


class WaitForCurtinEventsTask(BackgroundTask):

    def __init__(self, controller):
        self.controller = controller
        self.waited = 0.0

    def start(self):
        pass

    def _bg_run(self):
        while self.controller._event_indent and self.waited < 5.0:
            time.sleep(0.1)
            self.waited += 0.1
        log.debug("waited %s seconds for events to drain", self.waited)

    def end(self, observer, fut):
        # Will raise if command failed:
        fut.result()
        self.controller._install_event_start("final system configuration")
        observer.task_succeeded()


class InstallTask(BackgroundTask):

    def __init__(self, controller, step_name, func, *args, **kw):
        self.controller = controller
        self.step_name = step_name
        self.func = func
        self.args = args
        self.kw = kw

    def __repr__(self):
        return "InstallTask(%r, *%r, **%r)" % (self.func, self.args, self.kw)

    def start(self):
        self.controller._install_event_start(self.step_name)

    def _bg_run(self):
        self.func(*self.args, **self.kw)

    def end(self, observer, fut):
        # Will raise if command failed:
        fut.result()
        self.controller._install_event_finish()
        observer.task_succeeded()

    def cancel(self):
        pass


class InstallProgressController(BaseController):
    signals = [
        ('installprogress:filesystem-config-done', 'filesystem_config_done'),
        ('installprogress:identity-config-done',   'identity_config_done'),
        ('installprogress:ssh-config-done',        'ssh_config_done'),
        ('installprogress:snap-config-done',       'snap_config_done'),
    ]

    def __init__(self, common):
        super().__init__(common)
        self.answers = self.all_answers.get('InstallProgress', {})
        self.answers.setdefault('reboot', False)
        self.progress_view = None
        self.progress_view_showing = False
        self.install_state = InstallState.NOT_STARTED
        self.journal_listener_handle = None
        self._postinstall_prerequisites = {
            'install': False,
            'ssh': False,
            'identity': False,
            'snap': False,
            }
        self._event_indent = ""
        self._event_syslog_identifier = 'curtin_event.%s' % (os.getpid(),)
        self._log_syslog_identifier = 'curtin_log.%s' % (os.getpid(),)

    def tpath(self, *path):
        return os.path.join(self.base_model.target, *path)

    def filesystem_config_done(self):
        self.curtin_start_install()

    def _step_done(self, step):
        self._postinstall_prerequisites[step] = True
        if all(self._postinstall_prerequisites.values()):
            self.start_postinstall_configuration()

    def identity_config_done(self):
        self._step_done('identity')

    def ssh_config_done(self):
        self._step_done('ssh')

    def snap_config_done(self):
        self._step_done('snap')

    def curtin_error(self):
        log.debug('curtin_error')
        self.install_state = InstallState.ERROR
        self.progress_view.spinner.stop()
        self.progress_view.set_status(('info_error',
                                       _("An error has occurred")))
        self.progress_view.show_complete(True)
        self.default()

    def _bg_run_command_logged(self, cmd):
        cmd = ['systemd-cat', '--level-prefix=false',
               '--identifier=' + self._log_syslog_identifier] + cmd
        return utils.run_command(cmd)

    def _journal_event(self, event):
        if event['SYSLOG_IDENTIFIER'] == self._event_syslog_identifier:
            self.curtin_event(event)
        elif event['SYSLOG_IDENTIFIER'] == self._log_syslog_identifier:
            self.curtin_log(event)

    def _install_event_start(self, message):
        log.debug("_install_event_start %s", message)
        self.footer_description.set_text(message)
        self.progress_view.add_event(self._event_indent + message)
        self._event_indent += "  "
        self.footer_spinner.start()

    def _install_event_finish(self):
        self._event_indent = self._event_indent[:-2]
        log.debug("_install_event_finish %r", self._event_indent)
        self.footer_spinner.stop()

    def curtin_event(self, event):
        e = {}
        for k, v in event.items():
            if k.startswith("CURTIN_"):
                e[k] = v
        log.debug("curtin_event received %r", e)
        event_type = event.get("CURTIN_EVENT_TYPE")
        if event_type not in ['start', 'finish']:
            return
        if event_type == 'start':
            self._install_event_start(event.get("CURTIN_MESSAGE", "??"))
        if event_type == 'finish':
            self._install_event_finish()

    def curtin_log(self, event):
        self.progress_view.add_log_line(event['MESSAGE'])

    def start_journald_listener(self, identifiers, callback):
        reader = journal.Reader()
        args = []
        for identifier in identifiers:
            args.append("SYSLOG_IDENTIFIER={}".format(identifier))
        reader.add_match(*args)

        def watch():
            if reader.process() != journal.APPEND:
                return
            for event in reader:
                callback(event)
        return self.loop.watch_file(reader.fileno(), watch)

    def _write_config(self, path, config):
        with open(path, 'w') as conf:
            datestr = '# Autogenerated by SUbiquity: {} UTC\n'.format(
                str(datetime.datetime.utcnow()))
            conf.write(datestr)
            conf.write(yaml.dump(config))

    def _get_curtin_command(self):
        config_file_name = 'subiquity-curtin-install.conf'

        if self.opts.dry_run:
            log.debug("Installprogress: this is a dry-run")
            config_location = os.path.join('.subiquity/', config_file_name)
            curtin_cmd = ["python3", "scripts/replay-curtin-log.py",
                          "examples/curtin-events.json",
                          self._event_syslog_identifier]
        else:
            log.debug("Installprogress: this is the *REAL* thing")
            config_location = os.path.join('/var/log/installer',
                                           config_file_name)
            curtin_cmd = [sys.executable, '-m', 'curtin', '--showtrace', '-c',
                          config_location, 'install']

        ident = self._event_syslog_identifier
        self._write_config(config_location,
                           self.base_model.render(syslog_identifier=ident))

        return curtin_cmd

    def curtin_start_install(self):
        log.debug('Curtin Install: starting curtin')
        self.install_state = InstallState.RUNNING
        self.footer_description = urwid.Text(_("starting..."))
        self.progress_view = ProgressView(self)
        self.footer_spinner = self.progress_view.spinner

        self.ui.auto_footer = False
        self.ui.set_footer(urwid.Columns(
            [('pack', urwid.Text(_("Install in progress:"))),
             (self.footer_description),
             ('pack', self.footer_spinner)], dividechars=1))

        self.journal_listener_handle = self.start_journald_listener(
            [self._event_syslog_identifier, self._log_syslog_identifier],
            self._journal_event)

        curtin_cmd = self._get_curtin_command()

        log.debug('Curtin install cmd: {}'.format(curtin_cmd))
        self.run_in_bg(
            lambda: self._bg_run_command_logged(curtin_cmd),
            self.curtin_install_completed)

    def curtin_install_completed(self, fut):
        cp = fut.result()
        log.debug('curtin_install completed: %s', cp.returncode)
        if cp.returncode != 0:
            self.curtin_error()
            return
        self.install_state = InstallState.DONE
        log.debug('After curtin install OK')
        self.ui.progress_current += 1
        if not self.progress_view_showing:
            self.ui.set_footer(_("Install complete"))
        else:
            # Re-set footer so progress bar updates.
            self.ui.set_footer(_("Thank you for using Ubuntu!"))
        self._step_done('install')

    def cancel(self):
        pass

    def _bg_install_openssh_server(self):
        if self.opts.dry_run:
            cmd = [
                "sleep", str(2/self.scale_factor),
                ]
        else:
            cmd = [
                sys.executable, "-m", "curtin", "system-install", "-t",
                "/target",
                "--", "openssh-server",
                ]
        self._bg_run_command_logged(cmd)

    def _bg_cleanup_apt(self):
        if self.opts.dry_run:
            cmds = [["sleep", str(1/self.scale_factor)]]
        else:
            cmds = [
                ["umount", self.tpath('etc/apt')],
                ["umount", self.tpath('var/lib/apt/lists')],
                ]
        for cmd in cmds:
            self._bg_run_command_logged(cmd)

    def start_postinstall_configuration(self):
        self.copy_logs_to_target()

        class w(TaskWatcher):

            def __init__(self, controller):
                self.controller = controller

            def task_complete(self, stage):
                pass

            def task_error(self, stage, info):
                if isinstance(info, tuple):
                    tb = traceback.format_exception(*info)
                    self.controller.curtin_error("".join(tb))
                else:
                    self.controller.curtin_error()

            def tasks_finished(self):
                self.controller.loop.set_alarm_in(
                    0.0,
                    lambda loop, ud: self.controller.postinstall_complete())
        tasks = [
            ('drain', WaitForCurtinEventsTask(self)),
            ('cloud-init', InstallTask(
                self, "configuring cloud-init",
                self.base_model.configure_cloud_init)),
        ]
        if self.base_model.ssh.install_server:
            tasks.extend([
                ('install-ssh', InstallTask(
                    self, "installing OpenSSH server",
                    self._bg_install_openssh_server)),
                ])
        tasks.extend([
            ('cleanup', InstallTask(
                self, "restoring apt configuration",
                self._bg_cleanup_apt)),
            ])
        ts = TaskSequence(self.run_in_bg, tasks, w(self))
        ts.run()

    def postinstall_complete(self):
        self._install_event_finish()
        self.ui.set_header(_("Installation complete!"))
        self.progress_view.set_status(_("Finished install!"))
        self.progress_view.show_complete()

        if self.answers['reboot']:
            self.reboot()

    def copy_logs_to_target(self):
        if self.opts.dry_run:
            return
        target_logs = self.tpath('var/log/installer')
        utils.run_command(['cp', '-aT', '/var/log/installer', target_logs])
        try:
            with open(os.path.join(target_logs,
                                   'installer-journal.txt'), 'w') as output:
                utils.run_command(
                    ['journalctl'],
                    stdout=output, stderr=subprocess.STDOUT)
        except Exception:
            log.exception("saving journal failed")

    def reboot(self):
        if self.opts.dry_run:
            log.debug('dry-run enabled, skipping reboot, quiting instead')
            self.signal.emit_signal('quit')
        else:
            # TODO Possibly run this earlier, to show a warning; or
            # switch to shutdown if chreipl fails
            if platform.machine() == 's390x':
                utils.run_command(["chreipl", "/target/boot"])
            # Should probably run curtin -c $CONFIG unmount -t TARGET first.
            utils.run_command(["/sbin/reboot"])

    def quit(self):
        if not self.opts.dry_run:
            utils.disable_subiquity()
        self.signal.emit_signal('quit')

    def default(self):
        self.progress_view_showing = True
        if self.install_state == InstallState.RUNNING:
            self.progress_view.title = _("Installing system")
            footer = _("Thank you for using Ubuntu!")
        elif self.install_state == InstallState.DONE:
            self.progress_view.title = _("Install complete!")
            footer = _("Thank you for using Ubuntu!")
        elif self.install_state == InstallState.ERROR:
            self.progress_view.title = (
                _('An error occurred during installation'))
            footer = _('Please report this error in Launchpad')
        self.ui.set_body(self.progress_view)
        self.ui.set_footer(footer)
