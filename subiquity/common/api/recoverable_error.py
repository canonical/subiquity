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


class RecoverableError(Exception):
    """An error type that can be treated as non-fatal when raised from a
    request handler.

    The intention of this class is to provide enough information about the
    error to make it serializable into a Problem Details Object defined in RFC
    9457 (Problem Details for HTTP APIs).

    * The "code" attribute would be used as part of the "type" member of the
    Problem Details Object. Maybe using the tag URI scheme:
      tag:subiquity,2024-08-28:<code>
    * The "title" attribute would be used as the "title" member of the Problem
    Details Object.
    * As for the message of the exception, it could be used as the "detail"
    member of the Problem Details object."""

    # If this exception is uncaught in a request handler, what should we do.
    # By default we produce a crash report, but one can change set it to False.
    produce_crash_report = True

    # One must override title and code in subclasses with meaningful values.
    # Note that different instances of the same class will have the same title
    # and code. This is by design.
    code: str = ""
    title: str = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.title or not self.code:
            raise NotImplementedError(
                "Please do not instantiate directly. Use subclasses"
                " having a title and a user code properly set."
            )
