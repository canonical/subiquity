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
from abc import ABC, abstractmethod
from typing import Any

from subiquitycore.context import Context


class EventListener(ABC):
    """Interface for SubiquitySever event listeners"""

    @abstractmethod
    def report_start_event(self, context: Context, description: str) -> None:
        """Report a "start" event."""

    @abstractmethod
    def report_finish_event(
        self, context: Context, description: str, result: Any
    ) -> None:
        """Report a "finish" event."""

    @abstractmethod
    def report_info_event(self, context: Context, message: str) -> None:
        """Report an "info" event."""

    @abstractmethod
    def report_warning_event(self, context: Context, message: str) -> None:
        """Report a "warning" event."""

    @abstractmethod
    def report_error_event(self, context: Context, message: str) -> None:
        """Report an "error" event."""
