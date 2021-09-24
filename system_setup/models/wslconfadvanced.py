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

log = logging.getLogger('subiquity.models.wsl_configuration_advanced')


@attr.s
class WSLConfigurationAdvanced(object):
    gui_theme = attr.ib()
    gui_followwintheme = attr.ib()
    legacy_gui = attr.ib()
    legacy_audio = attr.ib()
    adv_ip_detect = attr.ib()
    wsl_motd_news = attr.ib()
    automount = attr.ib()
    mountfstab = attr.ib()
    interop_enabled = attr.ib()
    interop_appendwindowspath = attr.ib()


class WSLConfigurationAdvancedModel(object):
    """ Model representing integration
    """

    def __init__(self):
        self._wslconfadvanced = None
        # TODO WSL: Load settings from system

    def apply_settings(self, result, is_dry_run=False):
        d = {}
        # TODO: placholder settings; should be dynamically assgined using
        # ubuntu-wsl-integration
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
        self._wslconfadvanced = WSLConfigurationAdvanced(**d)
        # TODO WSL: Drop all calls of ubuntuwsl here and ensure the data
        # are passed to the app model
        if not is_dry_run:
            # reset to keep everything as refreshed as new
            run_command(["/usr/bin/ubuntuwsl", "reset", "-y"],
                        stdout=subprocess.DEVNULL)
            # set the settings
            # TODO: placholder settings; should be dynamically generated using
            # ubuntu-wsl-integration
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "WSL.automount.enabled", result.automount],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "WSL.automount.mountfstab", result.mountfstab],
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
                         "ubuntu.GUI.followwintheme",
                         result.gui_followwintheme],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "ubuntu.GUI.theme", result.gui_theme],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "ubuntu.Interop.guiintergration", result.legacy_gui],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "ubuntu.Interop.audiointegration",
                        result.legacy_audio],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "ubuntu.Interop.advancedipdetection",
                         result.adv_ip_detect],
                        stdout=subprocess.DEVNULL)
            run_command(["/usr/bin/ubuntuwsl", "update",
                         "ubuntu.Motd.wslnewsenabled", result.wsl_motd_news],
                        stdout=subprocess.DEVNULL)

    @property
    def wslconfadvanced(self):
        return self._wslconfadvanced

    def __repr__(self):
        return "<WSL Conf Advanced: {}>".format(self.wslconfadvanced)
