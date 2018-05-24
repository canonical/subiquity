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
import glob
import logging
import os
import shutil
import subprocess
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

TARGET = '/target'


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
        self.controller._install_event_start("installing snaps")
        observer.task_succeeded()


class DownloadSnapTask(BackgroundTask):
    # tl;dr: "snap download" makes me slightly sad
    #
    # When the user requests that a snap be installed, we need to
    # download the snap and associated assertion, put those in
    # /var/lib/snapd/seed/{snaps,assertions}/ and add it
    # /var/lib/snapd/seed/seed.yaml (all in the target system).  The
    # data in the seed.yaml is the name of the snap, the name of the
    # downloaded file and the channel to track.
    #
    # "snap download" downloads the snap and assertion for us but the
    # part that makes me slightly sad is that it doesn't tell us the
    # name of the files it downloaded in any reasonable way. We could
    # make some assumptions -- they're
    # ${SNAP_NAME}_${REVISION}.{snap,assert} and I don't think
    # SNAP_NAME or REVISION can contain underscores -- but this feels
    # a bit icky. So what I do is run each snap download in a separate
    # directory -- /var/lib/snapd/seed/tmp/$SNAP_NAME/ -- so
    # UpdateSnapSeed can be sure that the only snap/assertion in
    # /var/lib/snapd/seed/tmp/$SNAP_NAME/ is indeed the snap/assertion
    # for $SNAP_NAME.
    #
    # So after all the DownloadSnapTasks have run, the directory tree
    # looks like this:
    #
    # /var/lib/snapd/seed/
    #         seed.yaml -- seed that came from the base system
    #         snaps/
    #           [snaps from base seed]
    #         assertions/
    #           [assertions from base seed]
    #         tmp/
    #           $SNAP1/
    #             $SNAP1_$REV1.snap
    #             $SNAP1_$REV1.assert
    #           $SNAP2/
    #             $SNAP2_$REV2.snap
    #             $SNAP2_$REV2.assert
    #           ...
    #
    # UpdateSnapSeed turns this into:
    #
    # /var/lib/snapd/seed/
    #         seed.yaml -- updated seed
    #         snaps/
    #           [snaps from base seed]
    #           $SNAP1_$REV1.snap
    #           $SNAP2_$REV2.snap
    #           ...
    #         assertions/
    #           [assertions from base seed]
    #           $SNAP1_$REV1.assert
    #           $SNAP2_$REV2.assert
    #           ...

    def __init__(self, controller, tmp_dir, snap_name, channel):
        self.controller = controller
        self.this_snap_download_dir = os.path.join(tmp_dir, snap_name)
        self.snap_name = snap_name
        self.channel = channel

    def start(self):
        self.controller._install_event_start(
            _("downloading {}").format(self.snap_name))
        os.mkdir(self.this_snap_download_dir)
        self.proc = utils.start_command(
            ['snap', 'download', '--channel='+self.channel, self.snap_name],
            cwd=self.this_snap_download_dir)

    def _bg_run(self):
        stdout, stderr = self.proc.communicate()
        if self.proc.returncode != 0:
            raise subprocess.CalledProcessError(
                self.proc.returncode, self.proc.args, output=stdout,
                stderr=stderr)

    def end(self, observer, fut):
        self.controller._install_event_finish()
        try:
            fut.result()
        except BaseException:
            shutil.rmtree(self.this_snap_download_dir)
            raise
        else:
            observer.task_succeeded()


class UpdateSnapSeed(BackgroundTask):

    def __init__(self, controller, root):
        self.controller = controller
        self.seed_yaml = os.path.join(
            root, "var/lib/snapd/seed/seed.yaml")
        self.tmp_dir = os.path.join(
            root, "var/lib/snapd/seed/tmp")
        self.snap_dir = os.path.join(
            root, "var/lib/snapd/seed/snaps")
        self.assertions_dir = os.path.join(
            root, "var/lib/snapd/seed/assertions")

    def start(self):
        self.controller._install_event_start(_("updating snap seed"))

    def _bg_run(self):
        # This doesn't really need to be in the background, but as we
        # have the infrastructure already in place, we may as well.
        with open(self.seed_yaml) as fp:
            seed = yaml.safe_load(fp)

        to_install = self.controller.base_model.snaplist.to_install
        for snap_name in os.listdir(self.tmp_dir):
            this_snap_download_dir = os.path.join(self.tmp_dir, snap_name)
            [snap_path] = glob.glob(
                os.path.join(this_snap_download_dir, "*.snap"))
            [assertion_path] = glob.glob(
                os.path.join(this_snap_download_dir, "*.assert"))

            snap_file = os.path.basename(snap_path)
            assertion_file = os.path.basename(assertion_path)
            os.rename(
                snap_path,
                os.path.join(self.snap_dir, snap_file))
            os.rename(
                assertion_path,
                os.path.join(self.assertions_dir, assertion_file))

            # If this directory is not empty, something very
            # unexpected has happened and we should fail.
            os.rmdir(this_snap_download_dir)

            selection = to_install[snap_name]
            seedinfo = {
                'name': snap_name,
                'file': snap_file,
                'channel': selection.channel,
                }
            if selection.is_classic:
                seedinfo['classic'] = True
            seed['snaps'].append(seedinfo)

        # If the above loop did not empty this directory, again
        # something very unexpected has happened and we should fail.
        os.rmdir(self.tmp_dir)

        with open(self.seed_yaml, 'w') as fp:
            yaml.dump(seed, fp)

    def end(self, observer, fut):
        self.controller._install_event_finish()
        fut.result()
        observer.task_succeeded()


class SnapSeedTaskWatcher(TaskWatcher):
    def __init__(self, controller):
        self.controller = controller
        self.tasklist = []

    def task_complete(self, stage):
        self.tasklist.pop(0)

    def task_error(self, stage, info):
        if stage.startswith("download"):
            curtask = self.tasklist[0][1]
            explanation = None
            if isinstance(info, tuple):
                log.debug("xxx %s", info)
                if isinstance(info[1], subprocess.CalledProcessError):
                    explanation = info[1].stderr.strip()
                else:
                    explanation = "".join(traceback.format_exception(*info))
            self.controller.progress_view.ask_for_retry_snap(
                self, curtask.snap_name, explanation)
            return
        if isinstance(info, tuple):
            tb = traceback.format_exception(*info)
            self.controller.curtin_error("".join(tb))
        else:
            self.controller.curtin_error()

    def tasks_finished(self):
        self.controller._install_event_finish()
        self.controller.loop.set_alarm_in(
            0.0, lambda loop, ud: self.controller.postinstall_complete())


class InstallProgressController(BaseController):
    signals = [
        ('installprogress:filesystem-config-done', 'filesystem_config_done'),
        ('installprogress:identity-config-done',   'identity_config_done'),
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
        self._identity_config_done = False
        self._snap_config_done = False
        self._event_indent = ""
        self._event_syslog_identifier = 'curtin_event.%s' % (os.getpid(),)
        self._log_syslog_identifier = 'curtin_log.%s' % (os.getpid(),)

    def filesystem_config_done(self):
        self.curtin_start_install()

    def identity_config_done(self):
        if self.install_state == InstallState.DONE and \
          self._snap_config_done:
            self.postinstall_configuration()
        else:
            self._identity_config_done = True

    def snap_config_done(self):
        if self.install_state == InstallState.DONE and \
          self._identity_config_done:
            self.postinstall_configuration()
        else:
            self._snap_config_done = True

    def curtin_error(self, log_text=None):
        log.debug('curtin_error')
        if self.progress_view is None:
            self.progress_view = ProgressView(self)
        else:
            self.progress_view.spinner.stop()
        self.install_state = InstallState.ERROR
        if log_text is not None:
            self.progress_view.add_log_line(log_text)
        self.progress_view.set_status(
            ('info_error', _("An error has occurred")))
        self.progress_view.show_complete(True)
        self.default()

    def _bg_run_command_logged(self, cmd, env=None):
        cmd = ['systemd-cat', '--level-prefix=false',
               '--identifier=' + self._log_syslog_identifier] + cmd
        return utils.run_command(cmd, env=env)

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
            curtin_cmd = ['curtin', '--showtrace', '-c',
                          config_location, 'install']

        ident = self._event_syslog_identifier
        self._write_config(config_location,
                           self.base_model.render(target=TARGET,
                                                  syslog_identifier=ident))

        return curtin_cmd

    def curtin_start_install(self):
        log.debug('Curtin Install: starting curtin')
        self.install_state = InstallState.RUNNING
        self.footer_description = urwid.Text(_("starting..."))
        self.progress_view = ProgressView(self)
        self.footer_spinner = self.progress_view.spinner

        self.ui.set_footer(urwid.Columns(
            [('pack', urwid.Text(_("Install in progress:"))),
             (self.footer_description),
             ('pack', self.footer_spinner)], dividechars=1))

        self.journal_listener_handle = self.start_journald_listener(
            [self._event_syslog_identifier, self._log_syslog_identifier],
            self._journal_event)

        curtin_cmd = self._get_curtin_command()

        log.debug('Curtin install cmd: {}'.format(curtin_cmd))
        env = os.environ.copy()
        if 'SNAP' in env:
            del env['SNAP']
        self.run_in_bg(
            lambda: self._bg_run_command_logged(curtin_cmd, env),
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
        if self._identity_config_done and self._snap_config_done:
            self.postinstall_configuration()

    def cancel(self):
        pass

    def resume_snap_downloads(self, watcher, retry_cur_snap):
        if not retry_cur_snap:
            watcher.tasklist.pop(0)
        ts = TaskSequence(self.run_in_bg, watcher.tasklist, watcher)
        ts.run()

    def postinstall_configuration(self):
        log.debug("starting postinstall_configuration")
        self.configure_cloud_init()
        self.copy_logs_to_target()

        if self.base_model.snaplist.to_install:
            w = SnapSeedTaskWatcher(self)
            if self.opts.dry_run:
                root = '.subiquity'
                shutil.rmtree(
                    os.path.join(root, 'var/lib/snapd/seed'),
                    ignore_errors=True)
                os.makedirs(
                    os.path.join(root, 'var/lib/snapd/seed/snaps'))
                os.makedirs(
                    os.path.join(root, 'var/lib/snapd/seed/assertions'))
                fake_seed = ("snaps:\n"
                             "- name: core\n"
                             "  channel: stable\n"
                             "  file: core_XXXX.snap")
                seed_path = os.path.join(root, 'var/lib/snapd/seed/seed.yaml')
                with open(seed_path, 'w') as fp:
                    fp.write(fake_seed)
            else:
                root = TARGET
            tmp_dir = os.path.join(root, 'var/lib/snapd/seed/tmp')
            os.mkdir(tmp_dir)
            w.tasklist.append(('drain', WaitForCurtinEventsTask(self)))
            for snap_name, selection in sorted(
                    self.base_model.snaplist.to_install.items()):
                w.tasklist.append((
                    "download " + snap_name,
                    DownloadSnapTask(
                        self, tmp_dir, snap_name, selection.channel)
                    ))
            w.tasklist.append(("snapseed", UpdateSnapSeed(self, root)))
            ts = TaskSequence(self.run_in_bg, w.tasklist, w)
            ts.run()
        else:
            self.postinstall_complete()

    def postinstall_complete(self):
        self.ui.set_header(_("Installation complete!"))
        self.progress_view.set_status(_("Finished install!"))
        self.progress_view.show_complete()
        self.ui.progress_current += 1
        # Re-set footer so progress bar updates.
        self.ui.set_footer(_("Thank you for using Ubuntu!"))

        if self.answers['reboot']:
            self.reboot()

    def configure_cloud_init(self):
        if self.opts.dry_run:
            target = '.subiquity'
        else:
            target = TARGET
        self.base_model.configure_cloud_init(target)

    def copy_logs_to_target(self):
        if self.opts.dry_run:
            return
        utils.run_command(['cp', '-aT', '/var/log/installer',
                           '/target/var/log/installer'])
        try:
            with open('/target/var/log/installer/installer-journal.txt',
                      'w') as output:
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
            self.progress_view.footer = _("Thank you for using Ubuntu!")
        elif self.install_state == InstallState.DONE:
            self.progress_view.title = _("Install complete!")
            self.progress_view.footer = _("Thank you for using Ubuntu!")
        elif self.install_state == InstallState.ERROR:
            self.progress_view.title = (
                _('An error occurred during installation'))
            self.progress_view.footer = (
                _('Please report this error in Launchpad'))
        self.ui.set_body(self.progress_view)
