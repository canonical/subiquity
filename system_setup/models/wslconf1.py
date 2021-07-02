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

import logging
import subprocess
import attr

from subiquitycore.utils import run_command

log = logging.getLogger('subiquity.models.wsl_integration_1')


@attr.s
class WSLConfiguration1(object):
    custom_path = attr.ib()
    custom_mount_opt = attr.ib()
    gen_host = attr.ib()
    gen_resolvconf = attr.ib()


class WSLConfiguration1Model(object):
    """ Model representing integration
    """

    def __init__(self):
        self._wslconf1 = None

    def apply_settings(self, result, is_dry_run=False):
        d = {}
        d['custom_path'] = result.custom_path
        d['custom_mount_opt'] = result.custom_mount_opt
        d['gen_host'] = result.gen_host
        d['gen_resolvconf'] = result.gen_resolvconf
        self._wslconf1 = WSLConfiguration1(**d)
        if not is_dry_run:
            # reset to keep everything as refreshed as new
            run_command(["/usr/bin/ubuntuwsl", "reset", "-y"],
                        stdout=subprocess.DEVNULL)
            # set the settings
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "WSL.automount.root", result.custom_path],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "WSL.automount.options", result.custom_mount_opt],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "WSL.network.generatehosts", result.gen_host],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "WSL.network.generateresolvconf",
                        result.gen_resolvconf],
                        stdout=subprocess.DEVNULL)

    @property
    def wslconf1(self):
        return self._wslconf1

    def __repr__(self):
        return "<WSL Conf 1: {}>".format(self.wslconf1)
