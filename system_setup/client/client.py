# Copyright 2021 Canonical, Ltd.
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
import sys

from subiquity.client.client import SubiquityClient

log = logging.getLogger('system_setup.client.client')


class SystemSetupClient(SubiquityClient):

    from system_setup.client import controllers as controllers_mod

    snapd_socket_path = None

    controllers = [
        #"Serial",
        "Welcome",
        "WSLIdentity",
        "Integration",
        "Overview",
        "Progress",
        ]
    def __init__(self, opts):
        if opts.reconfigure:
            self.controllers = [
                "Welcome",
                "Reconfiguration",
                "Progress",
            ]
        super().__init__(opts)

    

    def restart(self, remove_last_screen=True, restart_server=False):
        log.debug(f"restart {remove_last_screen} {restart_server}")
        if self.fg_proc is not None:
            log.debug(
                "killing foreground process %s before restarting",
                self.fg_proc)
            self.restarting = True
            self.aio_loop.create_task(
                self._kill_fg_proc(remove_last_screen, restart_server))
            return
        if remove_last_screen:
            self._remove_last_screen()
        if restart_server:
            self.restarting = True
            self.ui.block_input = True
            self.aio_loop.create_task(self._restart_server())
            return
        if self.urwid_loop is not None:
            self.urwid_loop.stop()
        cmdline = sys.argv
        if self.opts.dry_run:
            cmdline = [
                sys.executable, '-m', 'system_setup.cmd.tui',
                ] + sys.argv[1:] + ['--socket', self.opts.socket]
            if self.opts.server_pid is not None:
                cmdline.extend(['--server-pid', self.opts.server_pid])
            log.debug("restarting %r", cmdline)

        os.execvp(cmdline[0], cmdline)
