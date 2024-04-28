# Copyright 2022 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging

import attr

log = logging.getLogger("system_setup.models.wslsetupoptions")


@attr.s
class WSLSetupOptions(object):
    install_language_support_packages = attr.ib()


class WSLSetupOptionsModel(object):
    """Model representing basic wsl configuration"""

    def __init__(self):
        self._wslsetupoptions = None

    def apply_settings(self, result):
        d = result.__dict__
        self._wslsetupoptions = WSLSetupOptions(**d)

    @property
    def wslsetupoptions(self):
        return self._wslsetupoptions

    def __repr__(self):
        return "<WSL Setup Options: {}>".format(self.wslsetupoptions)
