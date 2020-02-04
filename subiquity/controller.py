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

from subiquitycore.controller import (
    BaseController,
    RepeatedController,
    Skip,
    )

log = logging.getLogger("subiquity.controller")


class SubiquityController(BaseController):

    autoinstall_key = None
    autoinstall_default = None

    def __init__(self, app):
        super().__init__(app)
        self.autoinstall_applied = False
        if app.autoinstall_config:
            self.load_autoinstall_data(
                app.autoinstall_config.get(
                    self.autoinstall_key,
                    self.autoinstall_default))

    def load_autoinstall_data(self, data):
        """Load autoinstall data.

        This is called if there is an autoinstall happening. This
        controller may not have any data, and this controller may still
        be interactive.
        """
        pass

    async def apply_autoinstall_config(self):
        """Apply autoinstall configuration.

        This is only called for a non-interactive controller. It should
        block until the configuration has been applied. (self.configured()
        is called after this is done).
        """
        pass

    def interactive(self):
        if not self.app.autoinstall_config:
            return True
        i_sections = self.app.autoinstall_config.get(
            'interactive-sections', [])
        if '*' in i_sections or self.autoinstall_key in i_sections:
            return True
        return False

    def configured(self):
        """Let the world know that this controller's model is now configured.
        """
        if self.model_name is not None:
            self.app.base_model.configured(self.model_name)

    def deserialize(self, state):
        self.configured()


class NoUIController(SubiquityController):

    def start_ui(self):
        raise Skip

    def cancel(self):
        pass

    def interactive(self):
        return False


class RepeatedController(RepeatedController):

    def __init__(self, orig, index):
        super().__init__(orig, index)
        self.autoinstall_applied = False

    async def apply_autoinstall_config(self):
        await self.orig.apply_autoinstall_config(self.index)

    def configured(self):
        self.orig.configured()

    def interactive(self):
        return self.orig.interactive()
