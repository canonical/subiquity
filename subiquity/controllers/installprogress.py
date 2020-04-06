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

import asyncio
import contextlib
import datetime
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import traceback

from curtin.commands.install import (
    ERROR_TARFILE,
    INSTALL_LOG,
    )
from curtin.util import write_file

from systemd import journal

import yaml
from subiquitycore.async_helpers import (
    run_in_thread,
    schedule_task,
    )
from subiquitycore.context import Status
from subiquitycore.utils import (
    arun_command,
    astart_command,
    run_command,
    )

from subiquity.controller import SubiquityController
from subiquity.controllers.error import ErrorReportKind
from subiquity.ui.views.installprogress import ProgressView


log = logging.getLogger("subiquitycore.controller.installprogress")


class InstallState:
    NOT_STARTED = 0
    RUNNING = 1
    DONE = 2
    ERROR = -1


class TracebackExtractor:

    start_marker = re.compile(r"^Traceback \(most recent call last\):")
    end_marker = re.compile(r"\S")

    def __init__(self):
        self.traceback = []
        self.in_traceback = False

    def feed(self, line):
        if not self.traceback and self.start_marker.match(line):
            self.in_traceback = True
        elif self.in_traceback and self.end_marker.match(line):
            self.traceback.append(line)
            self.in_traceback = False
        if self.in_traceback:
            self.traceback.append(line)


def install_step(label, level=None, childlevel=None):
    def decorate(meth):
        name = meth.__name__

        async def decorated(self, context, *args):
            manager = self.install_context(
                context, name, label, level, childlevel)
            with manager as subcontext:
                await meth(self, subcontext, *args)
        return decorated
    return decorate


class InstallProgressController(SubiquityController):

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model
        self.progress_view = ProgressView(self)
        self.install_state = InstallState.NOT_STARTED
        self.journal_listener_handle = None

        self.reboot_clicked = asyncio.Event()
        if self.answers.get('reboot', False):
            self.reboot_clicked.set()

        self.uu = None
        self.uu_context = None
        self._event_syslog_identifier = 'curtin_event.%s' % (os.getpid(),)
        self._log_syslog_identifier = 'curtin_log.%s' % (os.getpid(),)
        self.tb_extractor = TracebackExtractor()
        self.curtin_event_contexts = {}
        self.confirmation = asyncio.Event()

    def interactive(self):
        return self.app.interactive()

    def start(self):
        self.install_task = schedule_task(self.install(self.context))

    async def apply_autoinstall_config(self):
        await self.install_task
        self.app.reboot_on_exit = True

    def tpath(self, *path):
        return os.path.join(self.model.target, *path)

    def curtin_error(self):
        self.install_state = InstallState.ERROR
        kw = {}
        if sys.exc_info()[0] is not None:
            log.exception("curtin_error")
            self.progress_view.add_log_line(traceback.format_exc())
        if self.tb_extractor.traceback:
            kw["Traceback"] = "\n".join(self.tb_extractor.traceback)
        crash_report = self.app.make_apport_report(
            ErrorReportKind.INSTALL_FAIL, "install failed", interrupt=False,
            **kw)
        self.progress_view.finish_all()
        self.progress_view.set_status(('info_error',
                                       _("An error has occurred")))
        self.start_ui()
        self.progress_view.show_error(crash_report)

    def logged_command(self, cmd):
        return ['systemd-cat', '--level-prefix=false',
                '--identifier=' + self._log_syslog_identifier] + cmd

    def _journal_event(self, event):
        if event['SYSLOG_IDENTIFIER'] == self._event_syslog_identifier:
            self.curtin_event(event)
        elif event['SYSLOG_IDENTIFIER'] == self._log_syslog_identifier:
            self.curtin_log(event)

    @contextlib.contextmanager
    def install_context(self, context, name, description,
                        level=None, childlevel=None):
        subcontext = context.child(name, description, level, childlevel)
        self.progress_view.event_start(subcontext, description)
        try:
            with subcontext:
                yield subcontext
        finally:
            self.progress_view.event_finish(subcontext)

    def curtin_event(self, event):
        e = {
            "EVENT_TYPE": "???",
            "MESSAGE": "???",
            "NAME": "???",
            "RESULT": "???",
            }
        prefix = "CURTIN_"
        for k, v in event.items():
            if k.startswith(prefix):
                e[k[len(prefix):]] = v
        event_type = e["EVENT_TYPE"]
        if event_type == 'start':
            def p(name):
                parts = name.split('/')
                for i in range(len(parts), -1, -1):
                    yield '/'.join(parts[:i]), '/'.join(parts[i:])

            cc = None
            for pre, post in p(e["NAME"]):
                if pre in self.curtin_event_contexts:
                    parent = self.curtin_event_contexts[pre]
                    cc = parent.child(post, e["MESSAGE"])
                    self.curtin_event_contexts[e["NAME"]] = cc
                    break
            if cc:
                cc.enter()
                self.progress_view.event_start(cc, e["MESSAGE"])
        if event_type == 'finish':
            status = getattr(Status, e["RESULT"], Status.WARN)
            cc = self.curtin_event_contexts.pop(e["NAME"], None)
            if cc is not None:
                cc.exit(status)
                self.progress_view.event_finish(cc)

    def curtin_log(self, event):
        log_line = event['MESSAGE']
        self.progress_view.add_log_line(log_line)
        self.tb_extractor.feed(log_line)

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
        loop = asyncio.get_event_loop()
        return loop.add_reader(reader.fileno(), watch)

    def _write_config(self, path, config):
        with open(path, 'w') as conf:
            datestr = '# Autogenerated by SUbiquity: {} UTC\n'.format(
                str(datetime.datetime.utcnow()))
            conf.write(datestr)
            conf.write(yaml.dump(config))

    def _get_curtin_command(self):
        config_file_name = 'subiquity-curtin-install.conf'

        if self.opts.dry_run:
            config_location = os.path.join('.subiquity/', config_file_name)
            log_location = '.subiquity/install.log'
            event_file = "examples/curtin-events.json"
            if 'install-fail' in self.app.debug_flags:
                event_file = "examples/curtin-events-fail.json"
            curtin_cmd = [
                "python3", "scripts/replay-curtin-log.py", event_file,
                self._event_syslog_identifier, log_location,
                ]
        else:
            config_location = os.path.join('/var/log/installer',
                                           config_file_name)
            curtin_cmd = [sys.executable, '-m', 'curtin', '--showtrace', '-c',
                          config_location, 'install']
            log_location = INSTALL_LOG

        ident = self._event_syslog_identifier
        self._write_config(config_location,
                           self.model.render(syslog_identifier=ident))

        self.app.note_file_for_apport("CurtinConfig", config_location)
        self.app.note_file_for_apport("CurtinLog", log_location)
        self.app.note_file_for_apport("CurtinErrors", ERROR_TARFILE)

        return curtin_cmd

    @install_step("umounting /target dir")
    async def unmount_target(self, context, target):
        cmd = [
            sys.executable, '-m', 'curtin', 'unmount',
            '-t', target,
            ]
        if self.opts.dry_run:
            cmd = ['sleep', str(0.2/self.app.scale_factor)]
        await arun_command(cmd)
        if not self.opts.dry_run:
            shutil.rmtree(target)

    @install_step("installing system", level="INFO", childlevel="DEBUG")
    async def curtin_install(self, context):
        log.debug('curtin_install')
        self.install_state = InstallState.RUNNING
        self.curtin_event_contexts[''] = context

        self.journal_listener_handle = self.start_journald_listener(
            [self._event_syslog_identifier, self._log_syslog_identifier],
            self._journal_event)

        curtin_cmd = self._get_curtin_command()

        log.debug('curtin install cmd: {}'.format(curtin_cmd))

        cp = await arun_command(
            self.logged_command(curtin_cmd), check=True)

        log.debug('curtin_install completed: %s', cp.returncode)

        self.install_state = InstallState.DONE
        log.debug('After curtin install OK')

    def cancel(self):
        pass

    async def install(self, context):
        try:
            await asyncio.wait(
                {e.wait() for e in self.model.install_events})

            await self.confirmation.wait()

            if os.path.exists(self.model.target):
                await self.unmount_target(context, self.model.target)

            await self.curtin_install(context)

            await asyncio.wait(
                {e.wait() for e in self.model.postinstall_events})

            await self.drain_curtin_events(context)

            await self.postinstall(context)

            self.ui.set_header(_("Installation complete!"))
            self.progress_view.set_status(_("Finished install!"))
            self.progress_view.show_complete()

            if self.model.network.has_network:
                self.progress_view.update_running()
                await self.run_unattended_upgrades(context)
                self.progress_view.update_done()

            await self.copy_logs_to_target(context)
        except Exception:
            self.curtin_error()
            if not self.interactive():
                raise

    async def move_on(self):
        await asyncio.wait(
            {self.reboot_clicked.wait(), self.install_task})
        self.app.reboot_on_exit = True
        if not self.opts.dry_run and platform.machine() == 's390x':
            run_command(["chreipl", "/target/boot"])
        self.app.next_screen()

    async def drain_curtin_events(self, context):
        waited = 0.0
        while self.progress_view.ongoing and waited < 5.0:
            await asyncio.sleep(0.1)
            waited += 0.1
        log.debug("waited %s seconds for events to drain", waited)
        self.curtin_event_contexts.pop('', None)

    @install_step(
        "final system configuration", level="INFO", childlevel="DEBUG")
    async def postinstall(self, context):
        autoinstall_path = os.path.join(
            self.app.root, 'var/log/installer/autoinstall-user-data')
        autoinstall_config = "#cloud-config\n" + yaml.dump(
            {"autoinstall": self.app.make_autoinstall()})
        write_file(autoinstall_path, autoinstall_config, mode=0o600)
        await self.configure_cloud_init(context)
        packages = []
        if self.model.ssh.install_server:
            packages = ['openssh-server']
        packages.extend(self.app.base_model.packages)
        for package in packages:
            subcontext = self.install_context(
                context,
                "install_{}".format(package),
                "installing {}".format(package))
            with subcontext:
                await self.install_package(package)
        await self.restore_apt_config(context)

    @install_step("configuring cloud-init")
    async def configure_cloud_init(self, context):
        await run_in_thread(self.model.configure_cloud_init)

    async def install_package(self, package):
        if self.opts.dry_run:
            cmd = ["sleep", str(2/self.app.scale_factor)]
        else:
            cmd = [
                sys.executable, "-m", "curtin", "system-install", "-t",
                "/target",
                "--", package,
                ]
        await arun_command(self.logged_command(cmd), check=True)

    @install_step("restoring apt configuration")
    async def restore_apt_config(self, context):
        if self.opts.dry_run:
            cmds = [["sleep", str(1/self.app.scale_factor)]]
        else:
            cmds = [
                ["umount", self.tpath('etc/apt')],
                ]
            if self.model.network.has_network:
                cmds.append([
                    sys.executable, "-m", "curtin", "in-target", "-t",
                    "/target", "--", "apt-get", "update",
                    ])
            else:
                cmds.append(["umount", self.tpath('var/lib/apt/lists')])
        for cmd in cmds:
            await arun_command(self.logged_command(cmd), check=True)

    @install_step("downloading and installing security updates")
    async def run_unattended_upgrades(self, context):
        target_tmp = os.path.join(self.model.target, "tmp")
        os.makedirs(target_tmp, exist_ok=True)
        apt_conf = tempfile.NamedTemporaryFile(
            dir=target_tmp, delete=False, mode='w')
        apt_conf.write(uu_apt_conf)
        apt_conf.close()
        env = os.environ.copy()
        env["APT_CONFIG"] = apt_conf.name[len(self.model.target):]
        self.uu_context = context
        if self.opts.dry_run:
            self.uu = await astart_command(self.logged_command([
                "sleep", str(5/self.app.scale_factor)]), env=env)
        else:
            self.uu = await astart_command(self.logged_command([
                sys.executable, "-m", "curtin", "in-target", "-t", "/target",
                "--", "unattended-upgrades", "-v",
                ]), env=env)
        await self.uu.communicate()
        self.uu = None
        self.uu_context = None
        os.remove(apt_conf.name)

    async def stop_uu(self):
        self.progress_view.event_finish(self.uu_context)
        with self.install_context(
                self.uu_context.parent,
                "stop_uu",
                "cancelling update"):
            if self.opts.dry_run:
                await asyncio.sleep(1)
                self.uu.terminate()
            else:
                await arun_command(self.logged_command([
                    'chroot', '/target',
                    '/usr/share/unattended-upgrades/'
                    'unattended-upgrade-shutdown',
                    '--stop-only',
                    ]), check=True)

    @install_step("copying logs to installed system")
    async def copy_logs_to_target(self, context):
        if self.opts.dry_run and 'copy-logs-fail' in self.app.debug_flags:
            raise PermissionError()
        target_logs = self.tpath('var/log/installer')
        if self.opts.dry_run:
            os.makedirs(target_logs, exist_ok=True)
        else:
            await arun_command(
                ['cp', '-aT', '/var/log/installer', target_logs])
        journal_txt = os.path.join(target_logs, 'installer-journal.txt')
        try:
            with open(journal_txt, 'w') as output:
                await arun_command(
                    ['journalctl', '-b'],
                    stdout=output, stderr=subprocess.STDOUT)
        except Exception:
            log.exception("saving journal failed")

    async def _click_reboot(self):
        if self.uu_context is not None:
            await self.stop_uu()
        self.reboot_clicked.set()

    def click_reboot(self):
        schedule_task(self._click_reboot())

    def start_ui(self):
        if self.install_state in [
                InstallState.NOT_STARTED,
                InstallState.RUNNING,
                ]:
            self.progress_view.title = _("Installing system")
        elif self.install_state == InstallState.DONE:
            self.progress_view.title = _("Install complete!")
        elif self.install_state == InstallState.ERROR:
            self.progress_view.title = (
                _('An error occurred during installation'))
        self.ui.set_body(self.progress_view)
        schedule_task(self.move_on())


uu_apt_conf = """\
# Config for the unattended-upgrades run to avoid failing on battery power or
# a metered connection.
Unattended-Upgrade::OnlyOnACPower "false";
Unattended-Upgrade::Skip-Updates-On-Metered-Connections "true";
"""
