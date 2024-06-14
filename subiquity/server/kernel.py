# Copyright 2023 Canonical, Ltd.
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

from subiquitycore.lsb_release import lsb_release


def flavor_to_pkgname(flavor: str, *, dry_run: bool) -> str:
    if flavor == "generic":
        return "linux-generic"
    if flavor == "hwe":
        flavor = "generic-hwe"

    release = lsb_release(dry_run=dry_run)["release"]
    # Should check this package exists really but
    # that's a bit tricky until we get cleverer about
    # the apt config in general.
    return f"linux-{flavor}-{release}"
