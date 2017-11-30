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

from setuptools import setup, find_packages
from DistUtilsExtra.command import build_extra
from DistUtilsExtra.command import build_i18n

import os
import sys

import subiquitycore

if sys.argv[-1] == 'clean':
    print("Cleaning up ...")
    os.system('rm -rf subiquity.egg-info build dist')
    sys.exit()

setup(name='subiquity',
      version=subiquitycore.__version__,
      description="Ubuntu Server Installer",
      long_description=__doc__,
      author='Canonical Engineering',
      author_email='ubuntu-dev@list.ubuntu.com',
      url='https://github.com/CanonicalLtd/suiquity',
      license="AGPLv2+",
      packages=find_packages(exclude=["tests"]),
      cmdclass={'build': build_extra.build_extra,
                'build_i18n': build_i18n.build_i18n, },
      data_files=[])
