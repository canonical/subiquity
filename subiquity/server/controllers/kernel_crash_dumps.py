# Copyright 2024 Canonical, Ltd.
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
from typing import TypedDict

from subiquity.server.controller import NonInteractiveController

log = logging.getLogger("subiquity.server.controllers.kernel_crash_dumps")


class KernelCrashDumpsConfig(TypedDict, total=True):
    enabled: bool | None


class KernelCrashDumpsController(NonInteractiveController):
    model_name = "kernel_crash_dumps"
    autoinstall_key = "kernel-crash-dumps"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "enabled": {"type": ["boolean", "null"]},
        },
        "required": ["enabled"],
        "additionalProperties": False,
    }

    def load_autoinstall_data(self, data: KernelCrashDumpsConfig | None) -> None:
        if data is None:
            return
        self.model.enabled = data["enabled"]

    def make_autoinstall(self) -> dict[str, KernelCrashDumpsConfig]:
        # Automatic determination implies no autoinstall
        if self.model.enabled is None:
            return {}

        return {"enabled": self.model.enabled}
