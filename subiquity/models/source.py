# Copyright 2021 Canonical, Ltd.
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
import os
import typing
import yaml

import attr

log = logging.getLogger('subiquity.models.source')


@attr.s(auto_attribs=True)
class CatalogEntry:
    variant: str
    id: str
    name: typing.Dict[str, str]
    description: typing.Dict[str, str]
    path: str
    size: int
    type: str
    default: bool = False


fake_entries = {
    'server': CatalogEntry(
        variant='server',
        id='synthesized',
        name={'en': 'Ubuntu Server'},
        description={'en': 'the default'},
        path='/media/filesystem',
        type='cp',
        default=True,
        size=2 << 30),
    'desktop': CatalogEntry(
        variant='desktop',
        id='synthesized',
        name={'en': 'Ubuntu Desktop'},
        description={'en': 'the default'},
        path='/media/filesystem',
        type='cp',
        default=True,
        size=5 << 30),
    }


class SourceModel:

    def __init__(self):
        self._dir = '/cdrom/casper'
        self.current = fake_entries['server']
        self.sources = [self.current]

    def load_from_file(self, fp):
        self._dir = os.path.dirname(fp.name)
        self.sources = []
        self.current = None
        entries = yaml.safe_load(fp)
        for entry in entries:
            kw = {}
            for field in attr.fields(CatalogEntry):
                if field.name in entry:
                    kw[field.name] = entry[field.name]
            c = CatalogEntry(**kw)
            self.sources.append(c)
            if c.default:
                self.current = c
        log.debug("loaded %d sources from %r", len(self.sources), fp.name)
        if self.current is None:
            self.current = self.sources[0]

    def render(self):
        path = os.path.join(self._dir, self.current.path)
        scheme = self.current.type
        return {
            'sources': {
                'ubuntu00': f'{scheme}://{path}'
                },
            }
