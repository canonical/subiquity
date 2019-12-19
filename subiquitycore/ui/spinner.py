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

from urwid import (
    Text,
    )

styles = {
    'dots': {
        'texts': [t.replace('*', '\N{bullet}')
                  for t in ['|*----|', '|-*---|', '|--*--|', '|---*-|',
                            '|----*|', '|---*-|', '|--*--|', '|-*---|']],
        'rate': 0.2,
        },
    'spin': {
        'texts': ['-', '\\', '|', '/'],
        'rate': 0.1,
        },
    }


class Spinner(Text):
    def __init__(self, aio_loop=None, style='spin', align='center'):
        self.aio_loop = aio_loop
        self.spin_index = 0
        self.spin_text = styles[style]['texts']
        self.rate = styles[style]['rate']
        super().__init__('', align=align)
        self.handle = None

    def spin(self):
        self.spin_index = (self.spin_index + 1) % len(self.spin_text)
        self.set_text(self.spin_text[self.spin_index])

    def _advance(self):
        self.spin()
        self.handle = self.aio_loop.call_later(self.rate, self._advance)

    def start(self):
        self.stop()
        self._advance()

    def stop(self):
        self.set_text('')
        if self.handle is not None:
            self.handle.cancel()
            self.handle = None
