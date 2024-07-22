# Copyright 2021 Canonical, Ltd.
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

from typing import List, Optional


class KernelModel:
    # The name of the kernel metapackage that we intend to install.
    metapkg_name: Optional[str] = None
    # During the installation, if we detect that a different kernel version is
    # needed (OEM being a common use-case), we can override the metapackage
    # name.
    metapkg_name_override: Optional[str] = None

    # If we explicitly request a kernel through autoinstall, this attribute
    # should be True.
    explicitly_requested: bool = False

    # In OEM kernel cases with a different kernel pre-installed in the source
    # image, we want to remove that pre-installed kernel.
    remove: Optional[List[str]] = None

    # If set to False, we won't request curthooks to install the kernel.
    # We can use this option if the kernel is already part of the source image
    # of if a kernel got installed using ubuntu-drivers.
    curthooks_install: bool = True

    @property
    def needed_kernel(self) -> Optional[str]:
        if self.metapkg_name_override is not None:
            return self.metapkg_name_override
        return self.metapkg_name

    def render(self):
        kernel = {}
        if self.curthooks_install:
            kernel["package"] = self.needed_kernel
        else:
            kernel["install"] = False
        if bool(self.remove):
            kernel["remove"] = self.remove
        else:
            kernel["remove_existing"] = True
        return {"kernel": kernel}
