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

black = 'black'                  # index 0
dark_red = 'dark red'            # index 1
dark_green = 'dark green'        # index 2
brown = 'brown'                  # index 3
dark_blue = 'dark blue'          # index 4 # This is overwritten to ubuntu orange at startup
dark_magenta = 'dark magenta'    # index 5
dark_cyan = 'dark cyan'          # index 6
light_gray = 'light gray'        # index 7
dark_gray = 'dark gray'          # index 8
light_red = 'light red'          # index 9
light_green = 'light green'      # index 10
yellow = 'yellow'                # index 11
light_blue = 'light blue'        # index 12
light_magenta = 'light magenta'  # index 13
light_cyan = 'light cyan'        # index 14
white = 'white'                  # index 15

orange = "#e51"
warm_gray = "g15"
cool_gray = "g50"

STYLES = [
    ('frame_header',        white,       dark_blue,     '', white,       orange),
    ('frame_footer',        white,       dark_gray,     '', white,       warm_gray),
    ('body',                white,       '',            '', white,       ''),
    ('menu_button',         white,       '',            '', white,       ''),
    ('menu_button focus',   black,       light_gray,    '', black,       light_gray),
    ('button',              white,       '',            '', white,       ''),
    ('button focus',        black,       dark_green,    '', black,       dark_green),
    ('danger_button',       white,       '',            '', white,       ''),
    ('danger_button focus', black,       dark_red,      '', black,       dark_red),
    ('cancel_button',       dark_cyan,   light_gray,    '', dark_cyan,   cool_gray), # also for "back" buttons
    ('cancel_button focus', black,       dark_cyan,     '', black,       dark_cyan),
    ('reset_button',        white,       '',            '', white,       ''),
    ('reset_button focus',  black,       dark_cyan,     '', black,       dark_cyan),
    ('save_button',         light_green, '',            '', light_green, cool_gray), # also for "ok" buttons
    ('save_button focus',   black,       dark_green,    '', black,       dark_green),
    ('info_primary',        white,       '',            '', white,       ''),
    ('info_major',          light_gray,  '',            '', light_gray,  ''),
    ('info_minor',          dark_gray,   '',            '', dark_gray,   ''),
    ('info_error',          dark_red,    '',            '', dark_red,    ''),
    ('string_input',        black,       light_gray,    '', black,       light_gray),
    ('string_input focus',  white,       dark_gray,     '', white,       dark_gray),
    ('progress_incomplete', white,       dark_magenta,  '', white,       dark_magenta),
    ('progress_complete',   white,       dark_blue,     '', white,       orange)
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
