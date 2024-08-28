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
    """An API-only error type that denotes a non-fatal error in a HTTP request
    handler."""

    # This field tells Subiquity what to do if an instance of this exception is
    # raised in a request handler.
    # By default we produce a crash report but one can decide otherwise by
    # changing this value to False. This can be done globally or by setting
    # produce_crash_report=False in a subclass. See
    # subiquity.server.controllers.filesystem.set_user_error_reportable for an
    # example.
    # Currently, this value also controls whether the error would lead to a 500
    # or 422 HTTP status.
    produce_crash_report = True
