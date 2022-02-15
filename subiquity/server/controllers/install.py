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

import logging
import os
import re
import shutil

from curtin.commands.install import (
    ERROR_TARFILE,
    INSTALL_LOG,
    )

import yaml

from subiquitycore.async_helpers import (
    run_in_thread,
    )
from subiquitycore.context import with_context
from subiquitycore.file_util import write_file, generate_config_yaml

from subiquity.common.errorreport import ErrorReportKind
from subiquity.common.types import (
    ApplicationState,
    )
from subiquity.journald import (
    journald_listen,
    )
from subiquity.server.controller import (
    SubiquityController,
    )
from subiquity.server.curtin import (
    run_curtin_command,
    start_curtin_command,
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


class InstallController(SubiquityController):

    def __init__(self, app):
        super().__init__(app)
        self.model = app.base_model

        self.unattended_upgrades_cmd = None
        self.unattended_upgrades_ctx = None
        self.tb_extractor = TracebackExtractor()

    def interactive(self):
        return True

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

    def write_config(self):
        config = self.model.render()
        config_location = '/var/log/installer/subiquity-curtin-install.conf'
        log_location = INSTALL_LOG
        if self.app.opts.dry_run:
            config_location = self.app.opts.output_base + config_location
            log_location = self.app.opts.output_base + INSTALL_LOG
        os.makedirs(os.path.dirname(config_location), exist_ok=True)
        os.makedirs(os.path.dirname(log_location), exist_ok=True)
        generate_config_yaml(config_location, config)
        self.app.note_file_for_apport("CurtinConfig", config_location)
        self.app.note_file_for_apport("CurtinErrors", ERROR_TARFILE)
        self.app.note_file_for_apport("CurtinLog", log_location)
        return config_location

    @with_context(description="umounting /target dir")
    async def unmount_target(self, *, context, target):
        await run_curtin_command(self.app, context, 'unmount', '-t', target,
                                 private_mounts=False)
        if not self.app.opts.dry_run:
            shutil.rmtree(target)

    @with_context(
        description="configuring apt", level="INFO", childlevel="DEBUG")
    async def configure_apt(self, *, context):
        mirror = self.app.controllers.Mirror
        configurer = await mirror.wait_config()
        return await configurer.configure_for_install(context)

    @with_context(
        description="installing system", level="INFO", childlevel="DEBUG")
    async def curtin_install(self, *, context, source):
        await run_curtin_command(self.app, context, 'install', source,
                                 config=self.write_config(),
                                 private_mounts=False)

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

            for_install_path = await self.configure_apt(context=context)

            if os.path.exists(self.model.target):
                await self.unmount_target(
                    context=context, target=self.model.target)

            await self.curtin_install(
                context=context, source='cp://' + for_install_path)

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
        write_file(autoinstall_path, autoinstall_config)
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
        await run_curtin_command(
            self.app, context, 'system-install', '-t', self.tpath(),
            '--', package,
            private_mounts=False)

    @with_context(description="restoring apt configuration")
    async def restore_apt_config(self, context):
        configurer = self.app.controllers.Mirror.apt_configurer
        await configurer.deconfigure(context, self.tpath())

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
            self.unattended_upgrades_cmd = await start_curtin_command(
                self.app, context, "in-target", "-t", self.tpath(),
                "--", "unattended-upgrades", "-v",
                private_mounts=True)
            await self.unattended_upgrades_cmd.wait()
            self.unattended_upgrades_cmd = None
            self.unattended_upgrades_ctx = None

    async def stop_unattended_upgrades(self):
        with self.unattended_upgrades_ctx.parent.child(
                "stop_unattended_upgrades",
                "cancelling update"):
            await self.app.command_runner.run([
                'chroot', self.tpath(),
                '/usr/share/unattended-upgrades/'
                'unattended-upgrade-shutdown',
                '--stop-only',
                ])
            if self.app.opts.dry_run and \
               self.unattended_upgrades_cmd is not None:
                self.unattended_upgrades_cmd.proc.terminate()


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
