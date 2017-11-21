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
    ("bg",        (0x00, 0x00, 0x00)),
    ("orange",    (0xe9, 0x54, 0x20)),
    ("danger",    (0xff, 0x00, 0x00)),
    ("good",      (0x00, 0xff, 0x00)),
    ("neutral",   (0x00, 0xff, 0xff)),
    ("gray",      (0x7f, 0x7f, 0x7f)),
    ("aubergine", (0x77, 0x21, 0x6f)),
    ("fg",        (0xff, 0xff, 0xff)),
]

STYLES = [
    ('frame_header',        'fg',      'orange'),
    ('frame_footer',        'fg',      'gray'),
    ('body',                'fg',      'bg'),
    ('menu_button',         'good',    'bg'),
    ('button',              'good',    'bg'),
    ('danger_button',       'danger',  'bg'),
    ('cancel_button',       'neutral', 'bg'),
    ('reset_button',        'neutral', 'bg'),
    ('save_button',         'good',    'bg'),
    ('info_primary',        'fg',      'bg'),
    ('info_minor',          'gray',    'bg'),
    ('info_error',          'danger',  'bg'),
    ('string_input',        'bg',      'gray'),
    ('string_input focus',  'bg',      'fg'),
    ('progress_incomplete', 'fg',      'aubergine'),
    ('progress_complete',   'fg',      'orange'),
    ('scrollbar_fg',        'orange',  'bg'),
    ('scrollbar_bg',        'fg',      'bg'),
]

focus_styles = set([
    'button',
    'menu_button',
    'danger_button',
    'cancel_button',
    'reset_button',
    'save_button',
    ])

for i in range(len(STYLES)):
    name, fg, bg = STYLES[i]
    if name in focus_styles:
        STYLES.append((name + ' focus', bg, fg))

STYLES_MONO = [
    ('frame_header',        'white', 'black'),
    ('frame_footer',        'white', 'black'),
    ('body',                'white', 'black'),
    ('info_minor',          'white', 'black'),
    ('menu_button',         '',      ''),
    ('menu_button focus',   '',      ''),
    ('button',              'white', 'black'),
    ('button focus',        'white', 'black'),
    ('string_input',        '',      ''),
    ('string_input focus',  '',      ''),
    ('progress_incomplete', '',      ''),
    ('progress_complete',   '',      ''),
]
