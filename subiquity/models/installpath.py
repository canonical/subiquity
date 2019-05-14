# Copyright 2018 Canonical, Ltd.
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

import logging


log = logging.getLogger("subiquity.models.installpath")


class InstallpathModel(object):
    """Model representing install options"""

    path = 'ubuntu'
    results = {}

    def __init__(self, target, sources=None):
        self.target = target
        self.cmdline_sources = sources
        self.sources = {}
        if sources:
            self.path = 'cmdline'

    @property
    def paths(self):
        cmdline = []
        if self.cmdline_sources:
            cmdline = [(_('Install from cli provided sources'), 'cmdline')]
        return cmdline + [
            (_('Install Ubuntu'), 'ubuntu'),
            (_('Exit To Shell'), 'execshell'),
        ]

    def update(self, results):
        self.results = results

    def render(self):
        src_map = {
            'ubuntu': ['cp:///media/filesystem'],
            'cmdline': self.cmdline_sources,
            }
        src_list = src_map[self.path]

        self.sources = {}
        for n, u in enumerate(src_list):
            self.sources[self.path + "%02d" % n] = u

        config = {
            'sources': self.sources,
            }

        return config
