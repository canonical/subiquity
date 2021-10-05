# Copyright 2019 Canonical, Ltd.
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

from subiquitycore.tuicontroller import (
    TuiController,
    )

log = logging.getLogger("subiquity.client.controller")


class Confirm(Exception):
    pass


class SubiquityTuiController(TuiController):

    endpoint_name = None

    def __init__(self, app):
        super().__init__(app)
        self.answers = app.answers.get(self.name, {})
        if self.endpoint_name is not None:
            self.endpoint = getattr(self.app.client, self.endpoint_name)
