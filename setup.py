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

import distutils.cmd
import distutils.command.build
import distutils.spawn
import glob
import os
import sys

from setuptools import setup, find_packages


class build_i18n(distutils.cmd.Command):

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        data_files = self.distribution.data_files

        with open('po/POTFILES.in') as in_fp:
            with open('po/POTFILES.in.tmp', 'w') as out_fp:
                for line in in_fp:
                    if line.startswith('['):
                        continue
                    out_fp.write('../' + line)

        os.chdir('po')
        distutils.spawn.spawn([
            'xgettext',
            '--directory=.',
            '--add-comments',
            '--from-code=UTF-8',
            '--keyword=pgettext:1c,2',
            '--output=subiquity.pot',
            '--files-from=POTFILES.in.tmp',
            ])
        os.chdir('..')
        os.unlink('po/POTFILES.in.tmp')

        for po_file in glob.glob("po/*.po"):
            lang = os.path.basename(po_file[:-3])
            mo_dir = os.path.join("build", "mo", lang, "LC_MESSAGES")
            mo_file = os.path.join(mo_dir, "subiquity.mo")
            if not os.path.exists(mo_dir):
                os.makedirs(mo_dir)
            distutils.spawn.spawn(["msgfmt", po_file, "-o", mo_file])
            targetpath = os.path.join("share/locale", lang, "LC_MESSAGES")
            data_files.append((targetpath, (mo_file,)))


class build(distutils.command.build.build):

    sub_commands = distutils.command.build.build.sub_commands + [
        ("build_i18n", None)]


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
              'subiquity-server = subiquity.cmd.server:main',
              'subiquity-tui = subiquity.cmd.tui:main',
              'console-conf-tui = console_conf.cmd.tui:main',
              ('console-conf-write-login-details = '
               'console_conf.cmd.write_login_details:main'),
          ],
      },
      data_files=[],
      cmdclass={
          'build': build,
          'build_i18n': build_i18n,
          },
      )
