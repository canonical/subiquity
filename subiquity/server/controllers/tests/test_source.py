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

import random
import unittest

import attr

from subiquitycore.tests.util import random_string

from subiquity.models.source import CatalogEntry
from subiquity.server.controllers.source import convert_source


def make_entry(**kw):
    fields = {
        'default': False,
        'name': {'en': random_string()},
        'description': {'en': random_string()},
        'size': random.randint(1000000, 2000000),
        }
    for field in attr.fields(CatalogEntry):
        if field.name not in fields:
            fields[field.name] = random_string()
    for k, v in kw.items():
        fields[k] = v
    return CatalogEntry(**fields)


class TestSubiquityModel(unittest.TestCase):

    def test_convert_source(self):
        entry = make_entry()
        source = convert_source(entry, 'C')
        self.assertEqual(source.id, entry.id)

    def test_convert_translations(self):
        entry = make_entry(
            name={
                'en': 'English',
                'fr': 'French',
                'fr_CA': 'French Canadian',
                })
        self.assertEqual(
            convert_source(entry, 'C').name, "English")
        self.assertEqual(
            convert_source(entry, 'en').name, "English")
        self.assertEqual(
            convert_source(entry, 'fr').name, "French")
        self.assertEqual(
            convert_source(entry, 'fr_CA').name, "French Canadian")
        self.assertEqual(
            convert_source(entry, 'fr_BE').name, "French")
