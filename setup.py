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

import os
import sys

setup_kwargs = {}
# dpkg build uses build and install, tox uses sdist
if 'SUBIQUITY_NO_I18N' not in os.environ:
    from DistUtilsExtra.command import build_extra
    from DistUtilsExtra.command import build_i18n
    setup_kwargs['cmdclass'] = {'build': build_extra.build_extra,
                                'build_i18n': build_i18n.build_i18n}


with open(os.path.join(os.path.dirname(__file__),
                       'subiquitycore', '__init__.py')) as init:
    lines = [line for line in init if 'i18n' not in line]
    ns = {}
    exec('\n'.join(lines), ns)
    version = ns['__version__']

if sys.argv[-1] == 'clean':
    print("Cleaning up ...")
    os.system('rm -rf subiquity.egg-info build dist')
    sys.exit()

setup(name='subiquity',
      version=version,
      description="Ubuntu Server Installer",
      long_description=__doc__,
      author='Canonical Engineering',
      author_email='ubuntu-dev@lists.ubuntu.com',
      url='https://github.com/CanonicalLtd/subiquity',
      license="AGPLv3+",
      packages=find_packages(exclude=["tests"]),
      scripts=[
          'bin/console-conf-wait',
          'bin/console-conf-wrapper',
          'bin/subiquity-debug',
          'bin/subiquity-configure-apt',
          'bin/subiquity-configure-run',
          'bin/subiquity-loadkeys',
          'bin/subiquity-service',
      ],
      entry_points={
          'console_scripts': [
              'subiquity-tui = subiquity.cmd.tui:main',
              'console-conf-tui = console_conf.cmd.tui:main',
              ('console-conf-write-login-details = '
               'console_conf.cmd.write_login_details:main'),
          ],
      },
      data_files=[],
      **setup_kwargs)
