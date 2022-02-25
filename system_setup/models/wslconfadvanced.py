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
import attr

log = logging.getLogger('system_setup.models.wslconfadvanced')


@attr.s
class WSLConfigurationAdvanced(object):
    gui_theme = attr.ib()
    gui_followwintheme = attr.ib()
    interop_guiintegration = attr.ib()
    interop_audiointegration = attr.ib()
    interop_advancedipdetection = attr.ib()
    motd_wslnewsenabled = attr.ib()
    automount_enabled = attr.ib()
    automount_mountfstab = attr.ib()
    interop_enabled = attr.ib()
    interop_appendwindowspath = attr.ib()


class WSLConfigurationAdvancedModel(object):
    """ Model representing integration
    """

    def __init__(self):
        self._wslconfadvanced = None

    def apply_settings(self, result):
        d = result.__dict__
        self._wslconfadvanced = WSLConfigurationAdvanced(**d)

    @property
    def wslconfadvanced(self):
        return self._wslconfadvanced

    def __repr__(self):
        return "<WSL Conf Advanced: {}>".format(self.wslconfadvanced)
