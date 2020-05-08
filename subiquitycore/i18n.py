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


from . import gettext38
import os
import syslog

syslog.syslog('i18n file is ' + __file__)
localedir = '/usr/share/locale'
if __file__.startswith('/snap/'):
    localedir = os.path.realpath(__file__ + '/../../../../../share/locale')
build_mo = os.path.realpath(__file__ + '/../../build/mo/')
if os.path.isdir(build_mo):
    localedir = build_mo
syslog.syslog('Final localedir is ' + localedir)


def switch_language(code='en_US'):
    syslog.syslog('switch_language ' + code)
    fake_trans = os.environ.get("FAKE_TRANSLATE", "0")
    if code != 'en_US' and fake_trans == "mangle":
        def my_gettext(message):
            return "_(%s)" % message
    elif fake_trans not in ("0", ""):
        def my_gettext(message):
            return message
    elif code:
        translation = gettext38.translation('subiquity', localedir=localedir,
                                            languages=[code], fallback=True)

        def my_gettext(message):
            if not message:
                return message
            return translation.gettext(message)
    import builtins
    builtins.__dict__['_'] = my_gettext


switch_language()

__all__ = ['switch_language']
