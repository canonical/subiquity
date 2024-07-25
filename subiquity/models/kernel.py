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

    # For the purposes of size and install speed, we want the default kernel
    # preinstalled in the source image.  There are several use cases to support
    # around this:
    # 1. no preinstall, no OEM kernel:
    #    Older ISOs do not have a kernel pre-installed, so we need to continue
    #    to be able to provide information about what kernel to install.
    #    Curtin manages this kernel installation historically, and we aren't
    #    changing that.
    # 2. yes preinstall, preinstalled kernel is wrong, no OEM kernel:
    #    Newer ISOs may have the wrong kernel pre-installed, so we need to
    #    install the correct kernel and remove the pre-installed one.  We
    #    continue to rely on curtin for kernel installation, with the addition
    #    of support to remove the pre-installed kernel.  remove_existing does
    #    the right thing here.
    # 3. yes preinstall, preinstalled kernel is right, no OEM kernel:
    #    Almost identical to case #2 but this time the preinstall is correct.
    #    This is the happy path and a noticeably faster install time.  From the
    #    subiquity perspective this is literally identical to #2, and how this
    #    plays out is that apt has nothing to install during curthooks.
    # 4. no preinstall, yes OEM kernel:
    #    This is almost like case #1 but subiquity is managing the kernel
    #    install, and it just tells curtin that no action is required.
    # 5. yes preinstall, preinstalled kernel is wrong, yes OEM kernel:
    #    This is similar to case #2, but the fact that subiquity manages the
    #    kernel install before curthooks means that calculating which kernel to
    #    remove is more complicated.  curtin needs to know which kernel was
    #    preinstalled, and we need to figure that out before the OEM kernel
    #    install happens.
    # 6. yes preinstall, preinstalled kernel is right, yes OEM kernel:
    #    A newer ISO may well have the same kernel installed that the OEM logic
    #    wants, which means we cannot remove the pre-installed kernel.

    # Understanding the next part is best done after a thorough read of
    # curtin's ensure_one_kernel() in curtin/distro.py

    # Handling:
    # 1. no preinstall, no OEM kernel:
    #    use "package" to specify the desired package, we set "remove_existing"
    #    but it has nothing to do, so nothing is removed.  Curtin carries out
    #    the actual kernel install.
    #    config: {"package": "foo", "remove_existing": True}
    # 2. yes preinstall, preinstalled kernel is wrong, no OEM kernel:
    #    use "package" to specify the desired package, we set "remove_existing"
    #    and this time it has a pre-installed package to remove.  Same config
    #    as #1, but curtin determines a package does need to be removed and
    #    does so.
    #    config: {"package": "foo", "remove_existing": True}
    # 3. yes preinstall, preinstalled kernel is right, no OEM kernel:
    #    use "package" to specify the desired package, we set "remove_existing"
    #    like before.  Same config as #1/#2, but curtin detects via
    #    ensure_one_kernel that the installed kernel state before/after
    #    installing the requested package is unchanged, so no kernel is
    #    removed.
    #    config: {"package": "foo", "remove_existing": True}
    # 4. no preinstall, yes OEM kernel:
    #    This time Subiquity is managing the kernel install, curtin should not
    #    install anything, and curtin's ensure_one_kernel would do the right
    #    thing but things are complicated by cases #5 and #6.
    #    config: {"install": False, "remove": []}
    # 5. yes preinstall, preinstalled kernel is wrong, yes OEM kernel:
    #    Again Subiquity has installed an OEM kernel, and again curtin has
    #    nothing to install but does need to do a remove.  Subiquity answers
    #    the remove question by listing the kernels preinstalled and supplying
    #    that to curtin, where ensure_one_kernel notices two kernels present
    #    and knows which one is preinstalled, so it can do the removal.
    #    config: {"install": False, "remove": ["foo"]}, where "foo" is the
    #    preinstalled kernel
    # 6. yes preinstall, preinstalled kernel is right, yes OEM kernel:
    #    Subiquity provides the same config here as #5, but in this case the
    #    OEM kernel install logic run by subiquity adds no new linux-image
    #    packages, so the functional difference here is curtin's
    #    ensure_one_kernel, like #3, has nothing to remove, it just needs a
    #    little help to know the starting (pre-OEM kernel install) state.  This
    #    is because curthooks run after the OEM kernel install, so the before
    #    state that ensure_one_kernel wants has to be calculated before the OEM
    #    kernel install.
    #    config: {"install": False, "remove": ["foo"]}, where "foo" is the
    #    preinstalled kernel
    # cases 4-6 all calculate their "remove" list by listing kernels that may
    # be present before doing the OEM kernel install, and ensure_one_kernel
    # handles the rest.

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
