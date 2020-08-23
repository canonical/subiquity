# Copyright 2020 Canonical, Ltd.
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


COLORS = [
    # black
    ("bg",        (0x11, 0x11, 0x11)),
    # dark red
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

PALETTE_COLOR = [
    ('frame_header_fringe', 'orange',  'bg'),
    ('frame_header',        'fg',      'orange'),
    ('body',                'fg',      'bg'),

    ('done_button',         'fg',      'bg'),
    ('danger_button',       'fg',      'bg'),
    ('other_button',        'fg',      'bg'),
    ('done_button focus',   'fg',      'good'),
    ('danger_button focus', 'fg',      'danger'),
    ('other_button focus',  'fg',      'gray'),

    ('menu_button',         'fg',      'bg'),
    ('menu_button focus',   'fg',      'gray'),

    ('frame_button',        'fg',      'orange'),
    ('frame_button focus',  'orange',  'fg'),

    ('info_primary',        'fg',      'bg'),
    ('info_minor',          'gray',    'bg'),
    ('info_minor header',   'gray',    'orange'),
    ('info_error',          'danger',  'bg'),

    ('string_input',        'bg',      'fg'),
    ('string_input focus',  'fg',      'gray'),

    ('progress_incomplete', 'fg',      'gray'),
    ('progress_complete',   'fg',      'neutral'),
    ('scrollbar',           'brand',   'bg'),
    ('scrollbar focus',     'gray',    'bg'),

    ('verified',            'good',    'bg'),
    ('verified header',     'good',    'orange'),
    ('verified focus',      'good',    'gray'),
]

PALETTE_MONO = [
    ('frame_header_fringe', 'white',   'black'),
    ('frame_header',        'black',   'white'),
    ('body',                'white',   'black'),

    ('done_button',         'white',   'black'),
    ('danger_button',       'white',   'black'),
    ('other_button',        'white',   'black'),
    ('done_button focus',   'black',   'white'),
    ('danger_button focus', 'black',   'white'),
    ('other_button focus',  'black',   'white'),

    ('menu_button',         'white',   'black'),
    ('menu_button focus',   'black',   'white'),
    ('frame_button',        'black',   'white'),
    ('frame_button focus',  'white',   'black'),

    ('info_primary',        'white',   'black'),
    ('info_minor',          'white',   'black'),
    ('info_minor header',   'black',   'white'),
    ('info_error',          'white',   'black'),

    ('string_input',        'white',   'black'),
    ('string_input focus',  'black',   'white'),

    ('progress_incomplete', 'white',   'black'),
    ('progress_complete',   'black',   'white'),
    ('scrollbar_fg',        'white',   'black'),
    ('scrollbar_bg',        'white',   'black'),
]

urwid_8_names = (
    'black',
    'dark red',
    'dark green',
    'brown',
    'dark blue',
    'dark magenta',
    'dark cyan',
    'light gray',
)


def _urwidize_palette(colors, styles):
    """Return a palette to be passed to MainLoop.

    colors is a list of exactly 8 tuples (name, (r, g, b))

    styles is a list of tuples (stylename, fg_color, bg_color) where
    fg_color and bg_color are defined in 'colors'
    """
    # The part that makes this "fun" is that urwid insists on referring
    # to the basic colors by their "standard" names but we overwrite
    # these colors to mean different things.  So we convert styles into
    # an urwid palette by mapping the names in colors to the standard
    # name.
    if len(colors) != 8:
        raise Exception(
            "make_palette must be passed a list of exactly 8 colors")
    urwid_name = dict(zip([c[0] for c in colors], urwid_8_names))

    urwid_palette = []
    for name, fg, bg in styles:
        urwid_fg, urwid_bg = urwid_name[fg], urwid_name[bg]
        urwid_palette.append((name, urwid_fg, urwid_bg))

    return urwid_palette


PALETTE_COLOR = _urwidize_palette(COLORS, PALETTE_COLOR)
