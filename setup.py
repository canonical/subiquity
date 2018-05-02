#!/usr/bin/env python3
# -*- mode: python; -*-
#
# Copyright 2015 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This package is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""
subiquity
=========
Ubuntu Server Installer
"""

from setuptools import setup, find_packages, Extension
from DistUtilsExtra.command import build_extra
from DistUtilsExtra.command import build_i18n

import os
import subprocess
import sys

import subiquitycore

if sys.argv[-1] == 'clean':
    print("Cleaning up ...")
    os.system('rm -rf subiquity.egg-info build dist')
    sys.exit()

def pkgconfig(package):
    return {
        'extra_compile_args': subprocess.check_output(['pkg-config', '--cflags', package]).decode('utf8').split(),
        'extra_link_args': subprocess.check_output(['pkg-config', '--libs', package]).decode('utf8').split(),
    }

setup(name='subiquity',
      version=subiquitycore.__version__,
      description="Ubuntu Server Installer",
      long_description=__doc__,
      author='Canonical Engineering',
      author_email='ubuntu-dev@lists.ubuntu.com',
      url='https://github.com/CanonicalLtd/subiquity',
      license="AGPLv3+",
      packages=find_packages(exclude=["tests"]),
      ext_modules=[
          Extension(
            "probert._rtnetlink",
            ['probert/_rtnetlinkmodule.c'],
            **pkgconfig("libnl-route-3.0")),
          Extension(
            "probert._nl80211",
            ['probert/_nl80211module.c'],
            **pkgconfig("libnl-genl-3.0")),
          ],
      cmdclass={'build': build_extra.build_extra,
                'build_i18n': build_i18n.build_i18n, },
      data_files=[])
