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
from typing import Any

log = logging.getLogger("subiquity.models.kernel_crash_dumps")


class KernelCrashDumpsModel:
    # Set to True/False via autoinstall. Defaults to None to let curtin know
    # to do dynamic enablement based on release, arch, etc.
    enabled: bool | None = None

    def render(self) -> dict[str, Any]:
        return {
            "kernel-crash-dumps": {
                "enabled": self.enabled,
            },
        }
