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

from subiquity.common.errorreport import ErrorReportKind
from subiquity.common.types import ApplicationState
from subiquity.server.controller import SubiquityController
from subiquitycore.context import with_context
from subiquitycore.utils import run_command
from system_setup.common.wsl_conf import wsl_config_update
from system_setup.common.wsl_utils import get_userandgroups

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

            dryrun = self.app.opts.dry_run
            variant = self.app.variant
            root_dir = self.model.root
            username = None
            if variant == "wsl_setup":
                wsl_id = self.model.identity.user
                username = wsl_id.username
                if dryrun:
                    log.debug("mimicking creating user %s",
                              wsl_id.username)
                else:
                    create_user_act = \
                        run_command(["/usr/sbin/useradd", "-m", "-s",
                                     "/bin/bash", "-p",
                                     wsl_id.password,
                                     wsl_id.username])
                    if create_user_act.returncode != 0:
                        raise Exception("Failed to create user %s: %s"
                                        % (wsl_id.username,
                                           create_user_act.stderr))
                    log.debug("created user %s", wsl_id.username)
                    assign_grp_act = \
                        run_command(["/usr/sbin/usermod", "-a",
                                     "-c", wsl_id.realname,
                                     "-G", get_userandgroups(),
                                     wsl_id.username])
                    if assign_grp_act.returncode != 0:
                        raise Exception(("Failed to assign group"
                                         " to user %s: %s")
                                        % (wsl_id.username,
                                           assign_grp_act.stderr))
            else:
                wsl_config_update(self.model.wslconfadvanced.wslconfadvanced,
                                  root_dir)

            # update advanced config when it is in autoinstall mode
            if self.app.opts.autoinstall is not None and \
               self.model.wslconfadvanced.wslconfadvanced is not None:
                wsl_config_update(self.model.wslconfadvanced.wslconfadvanced,
                                  root_dir)

            wsl_config_update(self.model.wslconfbase.wslconfbase, root_dir,
                              default_user=username)

            self.app.update_state(ApplicationState.DONE)
        except Exception:
            kw = {}
            self.app.make_apport_report(
                ErrorReportKind.INSTALL_FAIL, "configuration failed", **kw)
            raise

    def stop_uu(self):
        # This is a no-op to allow Shutdown controller to depend on this one
        pass
