# Copyright 2025 Canonical, Ltd.
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

from unittest import TestCase

import attr
import attrs

from subiquity.server.snapd.types import snapdtype
from subiquitycore.tests.parameterized import parameterized


class TestMetadataMerge(TestCase):
    @parameterized.expand(
        (
            # non-name metadata should be merged in
            ({"stuff": "things"}, {"stuff": "things", "name": "foo-bar"}),
            # a conflict on the metadata field name is overwritten
            ({"name": "foobar"}, {"name": "foo-bar"}),
        )
    )
    def test_merge(self, initial, expected):
        @snapdtype
        class MetadataMerge:
            foo_bar: int = attr.ib(metadata=initial)

        [field] = attrs.fields(MetadataMerge)
        self.assertEqual(expected, field.metadata)
