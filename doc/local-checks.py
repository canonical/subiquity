# Copyright 2026 Canonical, Ltd.
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

import pathlib
import sys

import distro_info


def main() -> int:
    udi = distro_info.UbuntuDistroInfo()

    def find_distro(codename: str, version: str):
        def filt(distro):
            return distro.codename == codename and distro.version == version
        return next(iter(filter(filt, udi.get_all(result="object"))))

    stable = udi.stable(result="object")
    devel = udi.devel(result="object")
    from docutils.core import publish_doctree

    substitutions = publish_doctree(pathlib.Path("reuse/substitutions.txt").read_text()).substitution_defs

    version = substitutions["ubuntu-latest-version"][0]
    codename = substitutions["ubuntu-latest-codename"][0]

    try:
        doc_distro = find_distro(version=version, codename=codename)
    except StopIteration:
        print(f"No matching Ubuntu distro for ({version}, {codename})", file=sys.stderr)

        try:
            find_distro(version=f"{version} LTS", codename=codename)
        except StopIteration:
            pass
        else:
            print(f'Try "{version} LTS" instead of "{version}"', file=sys.stderr)

        return 1

    if doc_distro not in (devel, stable):
        print(f"{doc_distro.codename} does not correspond to"
              f" the devel release (i.e., {devel.codename})"
              f" or the latest stable release (i.e., {stable.codename})",
              file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
