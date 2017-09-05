# Copyright 2017 Canonical, Ltd.
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


import gettext
import os
import syslog

syslog.syslog('i18n file is ' + __file__)
localedir = '/usr/share/locale'
if __file__.startswith('/snap/'):
    localedir = os.path.realpath(__file__ + '/../../../../../share/locale')
syslog.syslog('Final localedir is ' + localedir)
gettext.install('subiquity', localedir=localedir)

__all__ = []
