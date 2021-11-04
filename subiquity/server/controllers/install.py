# Copyright 2020 Canonical, Ltd.
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
import datetime
import json
import logging
import os
import re
import shutil
import subprocess
import sys

from curtin.commands.install import (
    ERROR_TARFILE,
    INSTALL_LOG,
    )
from curtin.util import write_file

import yaml

from subiquitycore.async_helpers import (
    run_in_thread,
    )
from subiquitycore.context import Status, with_context
from subiquitycore.utils import (
    astart_command,
    )

from subiquity.common.errorreport import ErrorReportKind
from subiquity.server.controller import (
    SubiquityController,
    )
from subiquity.common.types import (
    ApplicationState,
    )
from subiquity.journald import (
    journald_listen,
    )

log = logging.getLogger("subiquity.server.controllers.install")


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


class LoggedCommandRunner:

    def __init__(self, ident):
        self.ident = ident

    async def start(self, cmd):
        return await astart_command([
            'systemd-cat', '--level-prefix=false', '--identifier='+self.ident,
            ] + cmd)

    async def run(self, cmd):
        proc = await self.start(cmd)
        await proc.communicate()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
        else:
            return subprocess.CompletedProcess(cmd, proc.returncode)


class DryRunCommandRunner(LoggedCommandRunner):

    def __init__(self, ident, delay):
        super().__init__(ident)
        self.delay = delay

    async def start(self, cmd):
        if 'scripts/replay-curtin-log.py' in cmd:
            delay = 0
        else:
            cmd = ['echo', 'not running:'] + cmd
            if 'unattended-upgrades' in cmd:
                delay = 3*self.delay
            else:
                delay = self.delay
        proc = await super().start(cmd)
        await asyncio.sleep(delay)
        return proc


class CurtinCommandRunner:

    def __init__(self, runner, event_syslog_id, config_location):
        self.runner = runner
        self.event_syslog_id = event_syslog_id
        self.config_location = config_location
        self._event_contexts = {}
        journald_listen(
            asyncio.get_event_loop(), [event_syslog_id], self._event)

    def _event(self, event):
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

            curtin_ctx = None
            for pre, post in p(e["NAME"]):
                if pre in self._event_contexts:
                    parent = self._event_contexts[pre]
                    curtin_ctx = parent.child(post, e["MESSAGE"])
                    self._event_contexts[e["NAME"]] = curtin_ctx
                    break
            if curtin_ctx:
                curtin_ctx.enter()
        if event_type == 'finish':
            status = getattr(Status, e["RESULT"], Status.WARN)
            curtin_ctx = self._event_contexts.pop(e["NAME"], None)
            if curtin_ctx is not None:
                curtin_ctx.exit(result=status)

    def make_command(self, command, *args, **conf):
        cmd = [
            sys.executable, '-m', 'curtin', '--showtrace',
            '-c', self.config_location,
            ]
        for k, v in conf.items():
            cmd.extend(['--set', 'json:' + k + '=' + json.dumps(v)])
        cmd.append(command)
        cmd.extend(args)
        return cmd

    async def run(self, context, command, *args, **conf):
        self._event_contexts[''] = context
        await self.runner.run(self.make_command(command, *args, **conf))
        waited = 0.0
        while len(self._event_contexts) > 1 and waited < 5.0:
            await asyncio.sleep(0.1)
            waited += 0.1
            log.debug("waited %s seconds for events to drain", waited)
        self._event_contexts.pop('', None)


class DryRunCurtinCommandRunner(CurtinCommandRunner):

    event_file = 'examples/curtin-events.json'

    def make_command(self, command, *args, **conf):
        if command == 'install':
            return [
                sys.executable, "scripts/replay-curtin-log.py",
                self.event_file, self.event_syslog_id,
                '.subiquity' + INSTALL_LOG,
                ]
        else:
            return super().make_command(command, *args, **conf)


class FailingDryRunCurtinCommandRunner(DryRunCurtinCommandRunner):

    event_file = 'examples/curtin-events-fail.json'


class InstallController(SubiquityController):

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model

        self.unattended_upgrades_proc = None
        self.unattended_upgrades_ctx = None
        self._event_syslog_id = 'curtin_event.%s' % (os.getpid(),)
        self.tb_extractor = TracebackExtractor()
        if self.app.opts.dry_run:
            self.command_runner = DryRunCommandRunner(
                self.app.log_syslog_id, 2/self.app.scale_factor)
        else:
            self.command_runner = LoggedCommandRunner(self.app.log_syslog_id)
        self.curtin_runner = None

    def stop_uu(self):
        if self.app.state == ApplicationState.UU_RUNNING:
            self.app.update_state(ApplicationState.UU_CANCELLING)
            self.app.aio_loop.create_task(self.stop_unattended_upgrades())

    def start(self):
        journald_listen(
            self.app.aio_loop, [self.app.log_syslog_id], self.log_event)
        self.install_task = self.app.aio_loop.create_task(self.install())

    def tpath(self, *path):
        return os.path.join(self.model.target, *path)

    def log_event(self, event):
        self.tb_extractor.feed(event['MESSAGE'])

    def make_curtin_command_runner(self):
        config = self.model.render(syslog_identifier=self._event_syslog_id)
        config_location = '/var/log/installer/subiquity-curtin-install.conf'
        log_location = INSTALL_LOG
        if self.app.opts.dry_run:
            config_location = '.subiquity' + config_location
            log_location = '.subiquity' + INSTALL_LOG
        os.makedirs(os.path.dirname(config_location), exist_ok=True)
        os.makedirs(os.path.dirname(log_location), exist_ok=True)
        with open(config_location, 'w') as conf:
            datestr = '# Autogenerated by Subiquity: {} UTC\n'.format(
                str(datetime.datetime.utcnow()))
            conf.write(datestr)
            conf.write(yaml.dump(config))
        self.app.note_file_for_apport("CurtinConfig", config_location)
        self.app.note_file_for_apport("CurtinErrors", ERROR_TARFILE)
        self.app.note_file_for_apport("CurtinLog", log_location)
        if self.app.opts.dry_run:
            if 'install-fail' in self.app.debug_flags:
                cls = FailingDryRunCurtinCommandRunner
            else:
                cls = DryRunCurtinCommandRunner
        else:
            cls = CurtinCommandRunner
        self.curtin_runner = cls(
            self.command_runner, self._event_syslog_id, config_location)

    @with_context(description="umounting /target dir")
    async def unmount_target(self, *, context, target):
        await self.curtin_runner.run(context, 'unmount', '-t', target)
        if not self.app.opts.dry_run:
            shutil.rmtree(target)

    @with_context(
        description="installing system", level="INFO", childlevel="DEBUG")
    async def curtin_install(self, *, context):
        await self.curtin_runner.run(context, 'install')

    @with_context()
    async def install(self, *, context):
        context.set('is-install-context', True)
        try:
            while True:
                self.app.update_state(ApplicationState.WAITING)

                await self.model.wait_install()

                if not self.app.interactive:
                    if 'autoinstall' in self.app.kernel_cmdline:
                        self.model.confirm()

                self.app.update_state(ApplicationState.NEEDS_CONFIRMATION)

                if await self.model.wait_confirmation():
                    break

            self.app.update_state(ApplicationState.RUNNING)

            self.make_curtin_command_runner()

            if os.path.exists(self.model.target):
                await self.unmount_target(
                    context=context, target=self.model.target)

            await self.curtin_install(context=context)

            self.app.update_state(ApplicationState.POST_WAIT)

            await self.model.wait_postinstall()

            self.app.update_state(ApplicationState.POST_RUNNING)

            await self.postinstall(context=context)

            self.app.update_state(ApplicationState.DONE)
        except Exception:
            kw = {}
            if self.tb_extractor.traceback:
                kw["Traceback"] = "\n".join(self.tb_extractor.traceback)
            self.app.make_apport_report(
                ErrorReportKind.INSTALL_FAIL, "install failed", **kw)
            raise

    @with_context(
        description="final system configuration", level="INFO",
        childlevel="DEBUG")
    async def postinstall(self, *, context):
        autoinstall_path = os.path.join(
            self.app.root, 'var/log/installer/autoinstall-user-data')
        autoinstall_config = "#cloud-config\n" + yaml.dump(
            {"autoinstall": self.app.make_autoinstall()})
        write_file(autoinstall_path, autoinstall_config, mode=0o600)
        await self.configure_cloud_init(context=context)
        packages = await self.get_target_packages(context=context)
        for package in packages:
            await self.install_package(context=context, package=package)

        if self.model.network.has_network:
            self.app.update_state(ApplicationState.UU_RUNNING)
            policy = self.model.updates.updates
            await self.run_unattended_upgrades(context=context, policy=policy)
        await self.restore_apt_config(context=context)

    @with_context(description="configuring cloud-init")
    async def configure_cloud_init(self, context):
        await run_in_thread(self.model.configure_cloud_init)

    @with_context(description="calculating extra packages to install")
    async def get_target_packages(self, context):
        return await self.app.base_model.target_packages()

    @with_context(
        name="install_{package}",
        description="installing {package}")
    async def install_package(self, *, context, package):
        await self.curtin_runner.run(context, 'system-install', '--', package)

    @with_context(description="restoring apt configuration")
    async def restore_apt_config(self, context):
        await self.command_runner.run(["umount", self.tpath('etc/apt')])
        if self.model.network.has_network:
            await self.curtin_runner.run(
                context, "in-target", "-t", self.tpath(),
                "--", "apt-get", "update")
        else:
            await self.command_runner.run(
                ["umount", self.tpath('var/lib/apt/lists')])

    @with_context(description="downloading and installing {policy} updates")
    async def run_unattended_upgrades(self, context, policy):
        if self.app.opts.dry_run:
            aptdir = self.tpath("tmp")
        else:
            aptdir = self.tpath("etc/apt/apt.conf.d")
        os.makedirs(aptdir, exist_ok=True)
        apt_conf_contents = uu_apt_conf
        if policy == 'all':
            apt_conf_contents += uu_apt_conf_update_all
        else:
            apt_conf_contents += uu_apt_conf_update_security
        fname = 'zzzz-temp-installer-unattended-upgrade'
        with open(os.path.join(aptdir, fname), 'wb') as apt_conf:
            apt_conf.write(apt_conf_contents)
            apt_conf.close()
            self.unattended_upgrades_ctx = context
            self.unattended_upgrades_proc = await self.command_runner.start(
                self.curtin_runner.make_command(
                    "in-target", "-t", self.tpath(),
                    "--", "unattended-upgrades", "-v"))
            await self.unattended_upgrades_proc.communicate()
            self.unattended_upgrades_proc = None
            self.unattended_upgrades_ctx = None

    async def stop_unattended_upgrades(self):
        with self.unattended_upgrades_ctx.parent.child(
                "stop_unattended_upgrades",
                "cancelling update"):
            await self.command_runner.run([
                'chroot', self.tpath(),
                '/usr/share/unattended-upgrades/'
                'unattended-upgrade-shutdown',
                '--stop-only',
                ])
            if self.app.opts.dry_run and \
               self.unattended_upgrades_proc is not None:
                self.unattended_upgrades_proc.terminate()


uu_apt_conf = b"""\
# Config for the unattended-upgrades run to avoid failing on battery power or
# a metered connection.
Unattended-Upgrade::OnlyOnACPower "false";
Unattended-Upgrade::Skip-Updates-On-Metered-Connections "true";
"""

uu_apt_conf_update_security = b"""\
# A copy of the current default unattended-upgrades config to grab
# security.
Unattended-Upgrade::Allowed-Origins {
        "${distro_id}:${distro_codename}";
        "${distro_id}:${distro_codename}-security";
        "${distro_id}ESMApps:${distro_codename}-apps-security";
        "${distro_id}ESM:${distro_codename}-infra-security";
};
"""

uu_apt_conf_update_all = b"""\
# A modified version of the unattended-upgrades default Allowed-Origins
# to include updates in the permitted origins.
Unattended-Upgrade::Allowed-Origins {
        "${distro_id}:${distro_codename}";
        "${distro_id}:${distro_codename}-updates";
        "${distro_id}:${distro_codename}-security";
        "${distro_id}ESMApps:${distro_codename}-apps-security";
        "${distro_id}ESM:${distro_codename}-infra-security";
};
"""
