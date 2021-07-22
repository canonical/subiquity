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
import json

from subiquitycore.utils import run_command

log = logging.getLogger('subiquity.models.wsl_integration_2')


@attr.s
class WSLConfiguration2(object):
    gui_theme = attr.ib()
    gui_followwintheme = attr.ib()
    legacy_gui = attr.ib()
    legacy_audio = attr.ib()
    adv_ip_detect = attr.ib()
    wsl_motd_news = attr.ib()
    automount = attr.ib()
    mountfstab = attr.ib()
    custom_path = attr.ib()
    custom_mount_opt = attr.ib()
    gen_host = attr.ib()
    gen_resolvconf = attr.ib()
    interop_enabled = attr.ib()
    interop_appendwindowspath = attr.ib()


class WSLConfiguration2Model(object):
    """ Model representing integration
    """

    def __init__(self):
        self._wslconf2 = None

    def apply_settings(self, result, is_dry_run=False):
        d = {}
        #TODO: placholder settings; should be dynamically assgined using ubuntu-wsl-integration
        d['custom_path'] = result.custom_path
        d['custom_mount_opt'] = result.custom_mount_opt
        d['gen_host'] = result.gen_host
        d['gen_resolvconf'] = result.gen_resolvconf
        d['interop_enabled'] = result.interop_enabled
        d['interop_appendwindowspath'] = result.interop_appendwindowspath
        d['gui_theme'] = result.gui_theme
        d['gui_followwintheme'] = result.gui_followwintheme
        d['legacy_gui'] = result.legacy_gui
        d['legacy_audio'] = result.legacy_audio
        d['adv_ip_detect'] = result.adv_ip_detect
        d['wsl_motd_news'] = result.wsl_motd_news
        d['automount'] = result.automount
        d['mountfstab'] = result.mountfstab
        self._wslconf2 = WSLConfiguration2(**d)
        if not is_dry_run:
            # reset to keep everything as refreshed as new
            run_command(["/usr/bin/ubuntuwsl", "reset", "-y"],
                        stdout=subprocess.DEVNULL)
            # set the settings
            #TODO: placholder settings; should be dynamically generated using ubuntu-wsl-integration
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "WSL.automount.enabled", result.automount],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "WSL.automount.mountfstab", result.mountfstab],
                        stdout=subprocess.DEVNULL)
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
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "WSL.interop.enabled",
                        result.interop_enabled],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "WSL.interop.appendwindowspath",
                        result.interop_appendwindowspath],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "ubuntu.GUI.followwintheme", result.gui_followwintheme],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "ubuntu.GUI.theme", result.gui_theme],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "ubuntu.Interop.guiintergration", result.legacy_gui],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "ubuntu.Interop.audiointegration", result.legacy_audio],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "ubuntu.Interop.advancedipdetection", result.adv_ip_detect],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "ubuntu.Motd.wslnewsenabled", result.wsl_motd_news],
                        stdout=subprocess.DEVNULL)               
            

    @property
    def wslconf2(self):
        return self._wslconf2

    def __repr__(self):
        return "<WSL Conf 2: {}>".format(self.wslconf2)
