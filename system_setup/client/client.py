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
from subiquitycore.lsb_release import lsb_release

log = logging.getLogger("system_setup.client.client")

ABOUT_UBUNTU_WSL = _(
    """
Welcome to the {id} Installer!

A full Ubuntu environment, deeply integrated with Windows,
for Linux application development and execution.
Optimised for cloud, web, data science, IOT and fun!

The installer will guide you through installing {description}.

The installer only requires the up and down arrow keys, space (or
return) and the occasional bit of typing.

This is revision {snap_revision} of the installer.
"""
)


def _about_msg(msg, dry_run):
    info = lsb_release(dry_run=dry_run)
    newId = info["id"] + " WSL"
    info.update(
        {
            "id": newId,
            "description": info["description"].replace(info["id"], newId),
            "snap_revision": os.environ.get("SNAP_REVISION", "SNAP_REVISION"),
        }
    )
    return msg.format(**info)


class SystemSetupClient(SubiquityClient):
    from system_setup.client import controllers as controllers_mod

    snapd_socket_path = None

    variant = "wsl_setup"
    cmdline = sys.argv
    dryrun_cmdline_module = "system_setup.cmd.tui"

    controllers = [
        "Welcome",
        "WSLSetupOptions",
        "WSLIdentity",
        "Summary",
    ]

    variant_to_controllers = {
        "wsl_setup": controllers,
        "wsl_configuration": [
            "WSLConfigurationBase",
            "WSLConfigurationAdvanced",
            "Summary",
        ],
    }

    def __init__(self, opts):
        super().__init__(opts, _about_msg(ABOUT_UBUNTU_WSL, opts.dry_run))
