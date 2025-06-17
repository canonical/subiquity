# Copyright 2025 Canonical, Ltd.
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

import re

import attrs


@attrs.define(order=True)
class SnapdVersion:
    major: int
    minor: int
    patch: int = 0


class SnapdInfo:
    def __init__(self, snapdapi) -> None:
        self.snapdapi = snapdapi

    def _parse_version(self, version: str) -> SnapdVersion:
        """Parse a snapd version number. Accepted version numbers are of the form:
         * major.minor (e.g., 2.68)
         * major.minor.patch (e.g., 2.68.4)
         * major.minor+extra (e.g., 2.68+git58.6677899)
         * major.minor.patch+extra (e.g., 2.68.4+git58.6677899)
        Extra information is ignored.
        """
        pattern = re.compile(
            r"(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?(?P<extra>\+.*)?"
        )

        if m := pattern.fullmatch(version):
            fields = {
                "major": int(m.group("major")),
                "minor": int(m.group("minor")),
            }

            if (patch := m.group("patch")) is not None:
                fields["patch"] = int(patch)

            return SnapdVersion(**fields)

        raise ValueError(f"could not parse snapd version: {version}")

    async def version(self) -> SnapdVersion:
        result = await self.snapdapi.v2.snaps["snapd"].GET()

        return self._parse_version(result.version)

    async def has_beta_entropy_check(self) -> bool:
        return await self.version() >= SnapdVersion(2, 68)
