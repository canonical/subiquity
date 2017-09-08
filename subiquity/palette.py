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

""" Palette definitions """

dark_magenta = 'dark magenta'
light_magenta = 'light magenta'
light_green = 'light green'
dark_green = 'dark green'
white = 'white'
black = 'black'
light_gray = 'light gray'
dark_gray = 'dark gray'
dark_red = 'dark red'
light_red = 'light red'
orange = "#f60"
warm_gray = "g15"

STYLES = [
    ('frame_header',        '', '', '', white,      orange),
    ('frame_footer',        '', '', '', white,      warm_gray),
    ('body',                '', '', '', white,      ''),
    ('menu_button',         '', '', '', white,      ''),
    ('menu_button focus',   '', '', '', black,      light_gray),
    ('button',              '', '', '', white,      ''),
    ('button focus',        '', '', '', black,      dark_green),
    ('info_primary',        '', '', '', white,      ''),
    ('info_major',          '', '', '', light_gray, ''),
    ('info_minor',          '', '', '', dark_gray,  ''),
    ('info_error',          '', '', '', dark_red,   ''),
    ('string_input',        '', '', '', black,      light_gray),
    ('string_input focus',  '', '', '', white,      dark_gray),
    ('progress_incomplete', '', '', '', white,      dark_magenta),
    ('progress_complete',   '', '', '', white,      light_magenta)
]

STYLES_MONO = [
    ('frame_header',        white, black, '', '',    ''),
    ('frame_footer',        white, black, '', '',    ''),
    ('body',                white, black, '', '',    ''),
    ('info_minor',          white, black, '', '',    ''),
    ('menu_button',         '',    '',    '', white, ''),
    ('menu_button focus',   '',    '',    '', white, ''),
    ('button',              white, black, '', '',    ''),
    ('button focus',        white, black, '', '',    ''),
    ('string_input',        '',    '',    '', white, ''),
    ('string_input focus',  '',    '',    '', white, ''),
    ('progress_incomplete', '',    '',    '', '',    black),
    ('progress_complete',   '',    '',    '', '',    white),
]
