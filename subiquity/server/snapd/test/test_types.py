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
from unittest.mock import Mock

import attr
import attrs

from subiquity.server.snapd.types import KeyboardConfig, snapdtype
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


class TestKeyboardConfig(TestCase):
    @parameterized.expand(
        (
            # default us layout
            ("us", "", None, "us", "", []),
            # with toggle
            ("us", "", "alt_shift_toggle", "us", "", ["grp:alt_shift_toggle"]),
            # with variant
            ("us", "dvorak", None, "us", "dvorak", []),
            # with toggle and variant
            (
                "fr",
                "azerty",
                "alt_shift_toggle",
                "fr",
                "azerty",
                ["grp:alt_shift_toggle"],
            ),
            # with multi layout
            (
                "us,cz",
                ",bksl",
                "alt_shift_toggle",
                "us",
                "",
                ["grp:alt_shift_toggle"],
            ),
        )
    )
    def test_from_subiquity_kb_model(
        self,
        layout,
        variant,
        toggle,
        expected_layout,
        expected_variant,
        expected_options,
    ):
        kb = Mock()
        kb.setting.layout = layout
        kb.setting.variant = variant
        kb.setting.toggle = toggle
        config = KeyboardConfig.from_subiquity_kb_model(kb)
        self.assertEqual(config.model, "pc105")
        self.assertEqual(config.layout, expected_layout)
        self.assertEqual(config.variant, expected_variant)
        self.assertEqual(config.options, expected_options)
