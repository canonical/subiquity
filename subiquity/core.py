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

from subiquitycore.core import Application

from subiquity.models.subiquity import SubiquityModel

log = logging.getLogger('console_conf.core')


class Subiquity(Application):

    from subiquity.palette import COLORS, STYLES, STYLES_MONO

    project = "subiquity"

    model_class = SubiquityModel

    controllers = [
            "Welcome",
            "Keyboard",
            "Network",
            "Filesystem",
            "Identity",
            "InstallProgress",
    ]

    def __init__(self, ui, opts):
        super().__init__(ui, opts)
        self.common['ui'].progress_completion += 1
