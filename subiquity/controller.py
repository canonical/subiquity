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

import jsonschema

from subiquitycore.context import with_context
from subiquitycore.controller import (
    BaseController,
    )
from subiquitycore.tuicontroller import (
    RepeatedController,
    TuiController,
    )

log = logging.getLogger("subiquity.controller")


class SubiquityController(BaseController):

    autoinstall_key = None
    autoinstall_schema = None
    autoinstall_default = None

    def __init__(self, app):
        super().__init__(app)
        self.autoinstall_applied = False
        self.context.set('controller', self)
        self.setup_autoinstall()

    def interactive(self):
        return False

    def setup_autoinstall(self):
        if self.app.autoinstall_config:
            with self.context.child("load_autoinstall_data"):
                ai_data = self.app.autoinstall_config.get(
                    self.autoinstall_key,
                    self.autoinstall_default)
                if ai_data is not None and self.autoinstall_schema is not None:
                    jsonschema.validate(ai_data, self.autoinstall_schema)
                self.load_autoinstall_data(ai_data)

    def load_autoinstall_data(self, data):
        """Load autoinstall data.

        This is called if there is an autoinstall happening. This
        controller may not have any data, and this controller may still
        be interactive.
        """
        pass

    @with_context()
    async def apply_autoinstall_config(self, context):
        """Apply autoinstall configuration.

        This is only called for a non-interactive controller. It should
        block until the configuration has been applied. (self.configured()
        is called after this is done).
        """
        pass

    def configured(self):
        """Let the world know that this controller's model is now configured.
        """
        if self.model_name is not None:
            self.app.base_model.configured(self.model_name)

    def deserialize(self, state):
        pass

    def make_autoinstall(self):
        return {}


class SubiquityTuiController(SubiquityController, TuiController):

    def interactive(self):
        if not self.app.autoinstall_config:
            return True
        i_sections = self.app.autoinstall_config.get(
            'interactive-sections', [])
        if '*' in i_sections or self.autoinstall_key in i_sections:
            return True
        return False


class RepeatedController(RepeatedController):

    autoinstall_key = None
    autoinstall_schema = None

    def __init__(self, orig, index):
        super().__init__(orig, index)
        self.autoinstall_applied = False

    async def apply_autoinstall_config(self):
        await self.orig.apply_autoinstall_config(index=self.index)

    def configured(self):
        self.orig.configured()

    def interactive(self):
        return self.orig.interactive()

    def make_autoinstall(self):
        return {}
