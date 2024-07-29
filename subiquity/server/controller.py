# Copyright 2020 Canonical, Ltd.
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

import json
import logging
import os
from typing import Any, Optional

import jsonschema
from jsonschema.exceptions import ValidationError

from subiquity.common.api.server import bind
from subiquity.server.autoinstall import AutoinstallValidationError
from subiquity.server.types import InstallerChannels
from subiquitycore.context import with_context
from subiquitycore.controller import BaseController

log = logging.getLogger("subiquity.server.controller")


class SubiquityController(BaseController):
    autoinstall_key: Optional[str] = None
    autoinstall_schema: Any = None
    autoinstall_default: Any = None
    endpoint: Optional[type] = None

    # If we want to update the autoinstall_key, we can add the old value
    # here to keep being backwards compatible. The old value will be marked
    # deprecated in favor of autoinstall_key.
    autoinstall_key_alias: Optional[str] = None

    interactive_for_variants = None

    def __init__(self, app):
        super().__init__(app)
        self.context.set("controller", self)

    def validate_autoinstall(self, ai_data: dict) -> None:
        try:
            jsonschema.validate(ai_data, self.autoinstall_schema)

        except ValidationError as original_exception:
            section = self.autoinstall_key

            new_exception: AutoinstallValidationError = AutoinstallValidationError(
                section,
            )

            raise new_exception from original_exception

    def setup_autoinstall(self):
        if not self.app.autoinstall_config:
            return
        with self.context.child("load_autoinstall_data"):
            key_candidates = [self.autoinstall_key]
            if self.autoinstall_key_alias is not None:
                key_candidates.append(self.autoinstall_key_alias)

            for key in key_candidates:
                try:
                    ai_data = self.app.autoinstall_config[key]
                    break
                except KeyError:
                    pass
            else:
                ai_data = self.autoinstall_default

            if ai_data is not None and self.autoinstall_schema is not None:
                self.validate_autoinstall(ai_data)

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

    @property
    def _active(self):
        """Some controllers report interactivity based on what variant is in
        use, and set interactive_for_variants to control that.  A controller
        that hasn't opted-in to this behavior is presumed interactive if it
        has made it this far, assuming the model is required in the first
        place.  Otherwise, consult the list of interactive_for_variants to
        determine if it should be interactive.  Note that some contollers
        override interactive(), so refer to the controller of interest for full
        details.
        """
        if self.interactive_for_variants is None:
            if self.model_name is None:
                return True
            return self.app.base_model.is_model_required(self.model_name)
        variant = self.app.base_model.source.current.variant
        return variant in self.interactive_for_variants

    def interactive(self):
        if not self.app.autoinstall_config:
            return self._active
        i_sections = self.app.autoinstall_config.get("interactive-sections", [])

        if "*" in i_sections:
            return self._active

        if self.autoinstall_key in i_sections:
            return self._active

        if (
            self.autoinstall_key_alias is not None
            and self.autoinstall_key_alias in i_sections
        ):
            return self._active
        return False

    async def configured(self):
        """Let the world know that this controller's model is now configured."""
        with open(self.app.state_path("states", self.name), "w") as fp:
            json.dump(self.serialize(), fp)
        if self.model_name is not None:
            await self.app.hub.abroadcast(
                (InstallerChannels.CONFIGURED, self.model_name)
            )

    def load_state(self):
        state_path = self.app.state_path("states", self.name)
        if not os.path.exists(state_path):
            return
        with open(state_path) as fp:
            self.deserialize(json.load(fp))

    def deserialize(self, state):
        pass

    def make_autoinstall(self):
        return {}

    def add_routes(self, app):
        if self.endpoint is not None:
            bind(app.router, self.endpoint, self)


class NonInteractiveController(SubiquityController):
    def interactive(self):
        return False
