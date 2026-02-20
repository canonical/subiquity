# Copyright 2024 Canonical, Ltd.
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
from typing import Optional

from subiquity.server.nonreportable import NonReportableException

log = logging.getLogger("subiquity.server.autoinstall")


class AutoinstallError(NonReportableException):
    pass


class AutoinstallValidationError(AutoinstallError):
    def __init__(
        self,
        owner: str,
        details: Optional[str] = None,
    ):
        self.message = f"Malformed autoinstall in {owner!r} section"
        self.owner = owner
        super().__init__(self.message, details=details)


class AutoinstallUserSuppliedCmdError(AutoinstallError):
    def __init__(
        self,
        cmd: list[str],
        details: Optional[str] = None,
    ):
        self.message = f"Command execution failure: {cmd!r}"
        self.cmd = cmd
        super().__init__(self.message, details=details)
