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


COLORS = [
    # black
    ("bg",        (0x11, 0x11, 0x11)),
    # dark read
    ("danger",    (0xff, 0x00, 0x00)),
    # dark green
    ("good",      (0x0e, 0x84, 0x20)),
    # brown
    ("orange",    (0xe9, 0x54, 0x20)),
    # dark blue
    ("neutral",   (0x00, 0x7a, 0xa6)),
    # dark magenta
    ("brand",     (0x33, 0x33, 0x33)),
    # dark cyan
    ("gray",      (0x66, 0x66, 0x66)),
    # light gray
    ("fg",        (0xff, 0xff, 0xff)),
]

STYLES = [
    ('frame_header',        'fg',      'orange'),
    ('frame_footer',        'fg',      'brand'),
    ('body',                'fg',      'bg'),

    ('done_button',         'fg',      'bg'),
    ('danger_button',       'fg',      'bg'),
    ('other_button',        'fg',      'bg'),
    ('done_button focus',   'fg',      'good'),
    ('danger_button focus', 'fg',      'danger'),
    ('other_button focus',  'fg',      'gray'),

    ('menu_button',         'fg',      'bg'),
    ('menu_button focus',   'fg',      'gray'),

    ('info_primary',        'fg',      'bg'),
    ('info_minor',          'gray',    'bg'),
    ('info_error',          'danger',  'bg'),

    ('string_input',        'bg',      'fg'),
    ('string_input focus',  'fg',      'gray'),

    ('progress_incomplete', 'fg',      'gray'),
    ('progress_complete',   'fg',      'neutral'),
    ('scrollbar',           'brand',   'bg'),
    ('scrollbar focus',     'gray',    'bg'),

    ('verified',            'good',    'bg'),
    ('verified focus',      'good',    'gray'),
]


STYLES_MONO = [
    ('frame_header',        'white',   'black'),
    ('frame_footer',        'white',   'black'),
    ('body',                'white',   'black'),

    ('done_button',         'white',   'black'),
    ('danger_button',       'white',   'black'),
    ('other_button',        'white',   'black'),
    ('done_button focus',   'black',   'white'),
    ('danger_button focus', 'black',   'white'),
    ('other_button focus',  'black',   'white'),

    ('menu_button',         'white',   'black'),
    ('menu_button focus',   'black',   'white'),

    ('info_primary',        'white',   'black'),
    ('info_minor',          'white',   'black'),
    ('info_error',          'white',   'black'),

    ('string_input',        'white',   'black'),
    ('string_input focus',  'black',   'white'),

    ('progress_incomplete', 'white',   'black'),
    ('progress_complete',   'black',   'white'),
    ('scrollbar_fg',        'white',   'black'),
    ('scrollbar_bg',        'white',   'black'),
]
