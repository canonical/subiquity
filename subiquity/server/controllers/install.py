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
import contextlib
import datetime
import logging
import os
import re
import shutil
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
    arun_command,
    astart_command,
    )

from subiquity.common.errorreport import ErrorReportKind
from subiquity.server.controller import (
    SubiquityController,
    )
from subiquity.common.types import (
    ApplicationState,
    )
from subiquity.journald import journald_subscriptions

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


class InstallController(SubiquityController):

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model

        self.unattended_upgrades_proc = None
        self.unattended_upgrades_ctx = None
        self._event_syslog_id = 'curtin_event.%s' % (os.getpid(),)
        self.tb_extractor = TracebackExtractor()
        self.curtin_event_contexts = {}

    def stop_uu(self):
        if self.app.state == ApplicationState.UU_RUNNING:
            self.app.update_state(ApplicationState.UU_CANCELLING)
            self.app.aio_loop.create_task(self.stop_unattended_upgrades())

    def start(self):
        self.install_task = self.app.aio_loop.create_task(self.install())

    def tpath(self, *path):
        return os.path.join(self.model.target, *path)

    def logged_command(self, cmd):
        return ['systemd-cat', '--level-prefix=false',
                '--identifier=' + self.app.log_syslog_id] + cmd

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

            curtin_ctx = None
            for pre, post in p(e["NAME"]):
                if pre in self.curtin_event_contexts:
                    parent = self.curtin_event_contexts[pre]
                    curtin_ctx = parent.child(post, e["MESSAGE"])
                    self.curtin_event_contexts[e["NAME"]] = curtin_ctx
                    break
            if curtin_ctx:
                curtin_ctx.enter()
        if event_type == 'finish':
            status = getattr(Status, e["RESULT"], Status.WARN)
            curtin_ctx = self.curtin_event_contexts.pop(e["NAME"], None)
            if curtin_ctx is not None:
                curtin_ctx.exit(result=status)

    def log_event(self, event):
        self.tb_extractor.feed(event['MESSAGE'])

    def _write_config(self, path, config):
        with open(path, 'w') as conf:
            datestr = '# Autogenerated by Subiquity: {} UTC\n'.format(
                str(datetime.datetime.utcnow()))
            conf.write(datestr)
            conf.write(yaml.dump(config))

    def _get_curtin_command(self):
        config_file_name = 'subiquity-curtin-install.conf'

        if self.app.opts.dry_run:
            config_location = os.path.join('.subiquity/', config_file_name)
            log_location = '.subiquity/install.log'
            event_file = "examples/curtin-events.json"
            if 'install-fail' in self.app.debug_flags:
                event_file = "examples/curtin-events-fail.json"
            curtin_cmd = [
                "python3", "scripts/replay-curtin-log.py", event_file,
                self._event_syslog_id, log_location,
                ]
        else:
            config_location = os.path.join('/var/log/installer',
                                           config_file_name)
            curtin_cmd = [sys.executable, '-m', 'curtin', '--showtrace', '-c',
                          config_location, 'install']
            log_location = INSTALL_LOG

        ident = self._event_syslog_id
        self._write_config(config_location,
                           self.model.render(syslog_identifier=ident))

        self.app.note_file_for_apport("CurtinConfig", config_location)
        self.app.note_file_for_apport("CurtinLog", log_location)
        self.app.note_file_for_apport("CurtinErrors", ERROR_TARFILE)

        return curtin_cmd

    @with_context(description="umounting /target dir")
    async def unmount_target(self, *, context, target):
        cmd = [
            sys.executable, '-m', 'curtin', 'unmount',
            '-t', target,
            ]
        if self.app.opts.dry_run:
            cmd = ['sleep', str(0.2/self.app.scale_factor)]
        await arun_command(cmd)
        if not self.app.opts.dry_run:
            shutil.rmtree(target)

    @with_context(
        description="installing system", level="INFO", childlevel="DEBUG")
    async def curtin_install(self, *, context):
        log.debug('curtin_install')
        self.curtin_event_contexts[''] = context

        curtin_cmd = self._get_curtin_command()

        log.debug('curtin install cmd: {}'.format(curtin_cmd))

        cp = await arun_command(self.logged_command(curtin_cmd), check=True)

        log.debug('curtin_install completed: %s', cp.returncode)

    @with_context()
    async def install(self, *, context):
        context.set('is-install-context', True)
        try:
            await asyncio.wait({e.wait() for e in self.model.install_events})

            if not self.app.interactive:
                if 'autoinstall' in self.app.kernel_cmdline:
                    self.model.confirm()

            self.app.update_state(ApplicationState.NEEDS_CONFIRMATION)

            await self.model.confirmation.wait()

            self.app.update_state(ApplicationState.RUNNING)

            if os.path.exists(self.model.target):
                await self.unmount_target(
                    context=context, target=self.model.target)

            with journald_subscriptions(
                    self.app.aio_loop,
                    [(self.app.log_syslog_id, self.log_event),
                     (self._event_syslog_id, self.curtin_event)]):
                await self.curtin_install(context=context)
                await self.drain_curtin_events(context=context)

            self.app.update_state(ApplicationState.POST_WAIT)

            await asyncio.wait(
                {e.wait() for e in self.model.postinstall_events})

            self.app.update_state(ApplicationState.POST_RUNNING)

            await self.postinstall(context=context)

            if self.model.network.has_network:
                self.app.update_state(ApplicationState.UU_RUNNING)
                policy = self.model.updates.updates
                if policy != 'none':
                    await self.run_unattended_upgrades(context=context,
                                                       policy=policy)
                else:
                    with context.parent.child("install",
                                              "skipping updates per request"):
                        pass

            self.app.update_state(ApplicationState.DONE)
        except Exception:
            kw = {}
            if self.tb_extractor.traceback:
                kw["Traceback"] = "\n".join(self.tb_extractor.traceback)
            self.app.make_apport_report(
                ErrorReportKind.INSTALL_FAIL, "install failed", **kw)
            raise

    async def drain_curtin_events(self, *, context):
        waited = 0.0
        while len(self.curtin_event_contexts) > 1 and waited < 5.0:
            await asyncio.sleep(0.1)
            waited += 0.1
        log.debug("waited %s seconds for events to drain", waited)
        self.curtin_event_contexts.pop('', None)

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
        packages = []
        if self.model.ssh.install_server:
            packages = ['openssh-server']
        packages.extend(self.app.base_model.packages)
        for package in packages:
            await self.install_package(context=context, package=package)
        await self.restore_apt_config(context=context)

    @with_context(description="configuring cloud-init")
    async def configure_cloud_init(self, context):
        await run_in_thread(self.model.configure_cloud_init)

    @with_context(
        name="install_{package}",
        description="installing {package}")
    async def install_package(self, *, context, package):
        if self.app.opts.dry_run:
            cmd = ["sleep", str(2/self.app.scale_factor)]
        else:
            cmd = [
                sys.executable, "-m", "curtin", "system-install", "-t",
                "/target",
                "--", package,
                ]
        await arun_command(self.logged_command(cmd), check=True)

    @with_context(description="restoring apt configuration")
    async def restore_apt_config(self, context):
        if self.app.opts.dry_run:
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

    @with_context(description="downloading and installing {policy} updates")
    async def run_unattended_upgrades(self, context, policy):
        if self.app.opts.dry_run:
            command = ["sleep", str(5/self.app.scale_factor)]
            aptdir = os.path.join(self.model.target, "tmp")
        else:
            command = [sys.executable, "-m", "curtin", "in-target",
                       "-t", "/target", "--", "unattended-upgrades", "-v"]
            aptdir = os.path.join(self.model.target, "etc/apt/apt.conf.d")
        os.makedirs(aptdir, exist_ok=True)
        apt_conf_contents = uu_apt_conf
        if policy == 'all':
            apt_conf_contents += uu_apt_conf_update_all
        else:
            apt_conf_contents += uu_apt_conf_update_security
        fname = 'zzzz-temp-installer-unattended-upgrade'
        with external_temp_file(aptdir, fname) as apt_conf:
            apt_conf.write(apt_conf_contents)
            apt_conf.close()
            self.unattended_upgrades_ctx = context
            self.unattended_upgrades_proc = await astart_command(
                self.logged_command(command))
            await self.unattended_upgrades_proc.communicate()
            self.unattended_upgrades_proc = None
            self.unattended_upgrades_ctx = None

    async def stop_unattended_upgrades(self):
        with self.unattended_upgrades_ctx.parent.child(
                "stop_unattended_upgrades",
                "cancelling update"):
            if self.app.opts.dry_run:
                await asyncio.sleep(1)
                self.unattended_upgrades_proc.terminate()
            else:
                await arun_command(self.logged_command([
                    'chroot', '/target',
                    '/usr/share/unattended-upgrades/'
                    'unattended-upgrade-shutdown',
                    '--stop-only',
                    ]), check=True)


@contextlib.contextmanager
def external_temp_file(dir, fname):
    path = os.path.join(dir, fname)
    fid = open(path, 'wb')
    try:
        yield fid
    finally:
        fid.close()
        os.remove(path)


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
