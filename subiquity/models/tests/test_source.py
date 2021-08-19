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

import os
import random
import shutil
import tempfile
import unittest
import yaml

from subiquitycore.tests.util import random_string

from subiquity.models.source import (
    SourceModel,
    )


def make_entry(**fields):
    raw = {
        'name': {
            'en': random_string(),
            },
        'description': {
            'en': random_string(),
            },
        'id': random_string(),
        'type': random_string(),
        'variant': random_string(),
        'path': random_string(),
        'size': random.randint(1000000, 2000000),
        }
    for k, v in fields.items():
        raw[k] = v
    return raw


class TestMirrorModel(unittest.TestCase):

    def tdir(self):
        tdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tdir)
        return tdir

    def write_and_load_entries(self, model, entries, dir=None):
        if dir is None:
            dir = self.tdir()
        cat_path = os.path.join(dir, 'catalog.yaml')
        with open(cat_path, 'w') as fp:
            yaml.dump(entries, fp)
        with open(cat_path) as fp:
            model.load_from_file(fp)

    def test_initially_server(self):
        model = SourceModel()
        self.assertEqual(model.current.variant, 'server')

    def test_load_from_file_simple(self):
        entry = make_entry(id='id1')
        model = SourceModel()
        self.write_and_load_entries(model, [entry])
        self.assertEqual(model.current.id, 'id1')

    def test_load_from_file_ignores_extra_keys(self):
        entry = make_entry(id='id1', foobarbaz=random_string())
        model = SourceModel()
        self.write_and_load_entries(model, [entry])
        self.assertEqual(model.current.id, 'id1')

    def test_default(self):
        entries = [
            make_entry(id='id1'),
            make_entry(id='id2', default=True),
            make_entry(id='id3'),
            ]
        model = SourceModel()
        self.write_and_load_entries(model, entries)
        self.assertEqual(model.current.id, 'id2')

    def test_render_absolute(self):
        entry = make_entry(
            type='scheme',
            path='/foo/bar/baz',
            )
        model = SourceModel()
        self.write_and_load_entries(model, [entry])
        self.assertEqual(
            model.render(), {'sources': {'ubuntu00': 'scheme:///foo/bar/baz'}})

    def test_render_relative(self):
        dir = self.tdir()
        entry = make_entry(
            type='scheme',
            path='foo/bar/baz',
            )
        model = SourceModel()
        self.write_and_load_entries(model, [entry], dir)
        self.assertEqual(
            model.render(),
            {'sources': {'ubuntu00': f'scheme://{dir}/foo/bar/baz'}})

    def test_render_initial(self):
        model = SourceModel()
        self.assertEqual(
            model.render(),
            {'sources': {'ubuntu00': 'cp:///media/filesystem'}})
