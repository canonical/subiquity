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
import subprocess
from subiquitycore.utils import run_command

from subiquitycore.context import with_context

from subiquity.common.errorreport import ErrorReportKind
from subiquity.server.controller import (
    SubiquityController,
    )

from subiquity.common.types import (
    ApplicationState,
    )

log = logging.getLogger("system_setup.server.controllers.configure")


class ConfigureController(SubiquityController):

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.model = app.base_model

    def start(self):
        self.install_task = self.app.aio_loop.create_task(self.configure())

    @with_context(
        description="final system configuration", level="INFO",
        childlevel="DEBUG")
    async def configure(self, *, context):
        context.set('is-install-context', True)
        try:

            self.app.update_state(ApplicationState.WAITING)

            await self.model.wait_install()

            self.app.update_state(ApplicationState.NEEDS_CONFIRMATION)

            self.app.update_state(ApplicationState.RUNNING)

            await self.model.wait_postinstall()

            self.app.update_state(ApplicationState.POST_WAIT)

            # TODO WSL:
            # 1. Use self.model to get all data to commit
            # 2. Write directly (without wsl utilities) to wsl.conf and other
            #    fstab files
            # 3. If not in reconfigure mode: create User, otherwise just write
            #    wsl.conf files.
            # This must not use subprocesses.
            # If dry-run: write in .subiquity

            self.app.update_state(ApplicationState.POST_RUNNING)

            variant = self.app.variant
            if variant == "wsl_setup":
                wsl_identity = self.model.identity
                run_command(["/usr/sbin/useradd", "-m", "-s", "/bin/bash",
                             "-p", wsl_identity.password,
                             wsl_identity.username])
                run_command(["/usr/sbin/usermod", "-a",
                             "-c", wsl_identity.realname,
                             "-G", self.get_userandgroups(),
                             wsl_identity.username])

                wslconf_base = self.model.wslconfbase
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.automount.root",
                             wslconf_base.custom_path],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.automount.options",
                             wslconf_base.custom_mount_opt],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.network.generatehosts",
                             wslconf_base.gen_host],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.network.generateresolvconf",
                             wslconf_base.gen_resolvconf],
                            stdout=subprocess.DEVNULL)
            else:
                wslconf_ad = self.model.wslconfadvanced
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.automount.enabled",
                             wslconf_ad.automount],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.automount.mountfstab",
                             wslconf_ad.mountfstab],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.automount.root",
                             wslconf_ad.custom_path],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.automount.options",
                             wslconf_ad.custom_mount_opt],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.network.generatehosts",
                             wslconf_ad.gen_host],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.network.generateresolvconf",
                             wslconf_ad.gen_resolvconf],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.interop.enabled",
                             wslconf_ad.interop_enabled],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.interop.appendwindowspath",
                             wslconf_ad.interop_appendwindowspath],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "ubuntu.GUI.followwintheme",
                             wslconf_ad.gui_followwintheme],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "ubuntu.GUI.theme",
                             wslconf_ad.gui_theme],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "ubuntu.Interop.guiintergration",
                             wslconf_ad.legacy_gui],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "ubuntu.Interop.audiointegration",
                             wslconf_ad.legacy_audio],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "ubuntu.Interop.advancedipdetection",
                             wslconf_ad.adv_ip_detect],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "ubuntu.Motd.wslnewsenabled",
                             wslconf_ad.wsl_motd_news],
                            stdout=subprocess.DEVNULL)
   
                wslconf_base = self.model.wslconfbase
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.automount.root",
                             wslconf_base.custom_path],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.automount.options",
                             wslconf_base.custom_mount_opt],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.network.generatehosts",
                             wslconf_base.gen_host],
                            stdout=subprocess.DEVNULL)
                run_command(["/usr/bin/ubuntuwsl", "update",
                             "WSL.network.generateresolvconf",
                             wslconf_base.gen_resolvconf],
                            stdout=subprocess.DEVNULL)

            self.app.update_state(ApplicationState.DONE)
        except Exception:
            kw = {}
            self.app.make_apport_report(
                ErrorReportKind.INSTALL_FAIL, "configuration failed", **kw)
            raise

    def get_userandgroups(self):
        usergroups_path = '/usr/share/subiquity/users-and-groups'
        build_usergroups_path = \
            os.path.realpath(__file__ + '/../../../users-and-groups')
        if os.path.isfile(build_usergroups_path):
            usergroups_path = build_usergroups_path
        user_groups = set()
        if os.path.exists(usergroups_path):
            with open(usergroups_path) as fp:
                for line in fp:
                    line = line.strip()
                    if line.startswith('#') or not line:
                        continue
                    user_groups.add(line)
        oneline_usergroups = ",".join(user_groups)
        return oneline_usergroups

    def stop_uu(self):
        # This is a no-op to allow Shutdown controller to depend on this one
        pass
