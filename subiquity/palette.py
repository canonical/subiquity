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

""" Palette Loader """


def apply_default_colors(cls):
    color_map = {'orange': '#d51',
                 'light_orange': '#d81',
                 'white': 'white',
                 'black': 'black',
                 'light_aubergine': '#77216F',
                 'mid_aubergine': '#5E2750',
                 'dark_aubergine': '#2C001E',
                 'warm_grey': '#AEA79F',
                 'cool_grey': '#333',
                 'small_dot_grey': '#AEA79F',
                 'text_grey': '#333'}
    for k, v in color_map.items():
        setattr(cls, k, v)
    return cls


@apply_default_colors
class Palette:
    pass

STYLES = [('frame_header', Palette.white, Palette.black,
           'default', Palette.white, Palette.orange),
          ('frame_footer', Palette.white, Palette.black),
          ('body', Palette.white, 'default', 'default',
           Palette.white, Palette.orange),
          ('button_primary', Palette.white, 'default',
           'default', Palette.white, Palette.cool_grey),
          ('button_primary focus', Palette.white,
           'default', 'default', Palette.white,
           Palette.light_orange),
          ('button_secondary', Palette.white, 'default',
           'default', Palette.white, Palette.cool_grey),
          ('button_secondary focus', Palette.white,
           'default', 'default', Palette.white, Palette.light_orange)]
