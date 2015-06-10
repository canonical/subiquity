# Copyright 2015 Canonical, Ltd.
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

""" UI utilities """

from urwid import Padding as _Padding
from functools import partialmethod


def apply_padders(cls):
    """ Decorator for generating useful padding methods

    Loops through and generates methods like:

      Padding.push_1(Widget)

      Sets the left padding attribute by 1

      Padding.pull_24(Widget)

      Sets right padding attribute by 24.

      Padding.center_50(Widget)

      Provides center padding with a relative width of 50
    """
    padding_count = 100

    for i in range(1, padding_count):
        setattr(cls, 'push_{}'.format(i), partialmethod(_Padding, left=i))
        setattr(cls, 'pull_{}'.format(i), partialmethod(_Padding, right=i))
        setattr(cls, 'center_{}'.format(i),
                partialmethod(_Padding, align='center',
                              width=('relative', i)))
        setattr(cls, 'left_{}'.format(i),
                partialmethod(_Padding, align='left',
                              width=('relative', i)))
        setattr(cls, 'right_{}'.format(i),
                partialmethod(_Padding, align='right',
                              width=('relative', i)))
    return cls


@apply_padders
class Padding:
    pass
