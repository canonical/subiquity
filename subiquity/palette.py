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
                 'light_orange': '#d31',
                 'white': 'white',
                 'black': 'black',
                 'light_aubergine': '#719',
                 'mid_aubergine': '#525',
                 'dark_aubergine': '#201',
                 'warm_grey': '#aaa',
                 'cool_grey': '#666',
                 'text_grey': '#333'}
    for k, v in color_map.items():
        setattr(cls, k, v)
    return cls


@apply_default_colors
class Palette:
    pass

STYLES = [
    ('frame_header', '', '', '',
     Palette.white, Palette.orange),
    ('frame_footer', '', '', '',
     Palette.white, Palette.orange),
    ('body', '', '', '',
     Palette.white, Palette.black),
    ('button_primary', '', '',
     '', Palette.white, Palette.cool_grey),
    ('button_primary focus', '', '', '',
     Palette.white, Palette.light_orange),
    ('button_secondary', '', '', '',
     Palette.white, Palette.cool_grey),
    ('button_secondary focus', '', '', '',
     Palette.white, Palette.light_orange),
    ('info_minor', '', '', '',
     Palette.text_grey, Palette.black)
]

STYLES_MONO = [('frame_header', Palette.white, Palette.black,
                '', '', ''),
               ('frame_footer', Palette.white, Palette.black,
                '', '', ''),
               ('body', Palette.white, Palette.black,
                '', '', ''),
               ('info_minor', Palette.white, Palette.black,
                '', '', ''),
               ('button_primary', Palette.white, Palette.black,
                '', '', ''),
               ('button_primary focus', Palette.white, Palette.black,
                '', '', ''),
               ('button_secondary', Palette.white, Palette.black,
                '', '', ''),
               ('button_secondary focus', Palette.white, Palette.black,
                '', '', '')]
