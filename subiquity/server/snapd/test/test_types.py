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
    def test_default_us_layout(self):
        kb = Mock()
        kb.setting.layout = "us"
        kb.setting.variant = ""
        kb.setting.toggle = None
        config = KeyboardConfig.from_subiquity_kb_model(kb)
        self.assertEqual(config.model, "pc105")
        self.assertEqual(config.layout, "us")
        self.assertEqual(config.variant, "")
        self.assertEqual(config.options, [])

    def test_with_toggle(self):
        kb = Mock()
        kb.setting.layout = "us"
        kb.setting.variant = ""
        kb.setting.toggle = "alt_shift_toggle"
        config = KeyboardConfig.from_subiquity_kb_model(kb)
        self.assertEqual(config.model, "pc105")
        self.assertEqual(config.layout, "us")
        self.assertEqual(config.variant, "")
        self.assertEqual(config.options, ["grp:alt_shift_toggle"])

    def test_with_variant(self):
        kb = Mock()
        kb.setting.layout = "us"
        kb.setting.variant = "dvorak"
        kb.setting.toggle = None
        config = KeyboardConfig.from_subiquity_kb_model(kb)
        self.assertEqual(config.model, "pc105")
        self.assertEqual(config.layout, "us")
        self.assertEqual(config.variant, "dvorak")
        self.assertEqual(config.options, [])

    def test_with_toggle_and_variant(self):
        kb = Mock()
        kb.setting.layout = "fr"
        kb.setting.variant = "azerty"
        kb.setting.toggle = "alt_shift_toggle"
        config = KeyboardConfig.from_subiquity_kb_model(kb)
        self.assertEqual(config.model, "pc105")
        self.assertEqual(config.layout, "fr")
        self.assertEqual(config.variant, "azerty")
        self.assertEqual(config.options, ["grp:alt_shift_toggle"])

    def test_with_multi_layout(self):
        kb = Mock()
        kb.setting.layout = "us,cz"
        kb.setting.variant = ",bksl"
        kb.setting.toggle = "alt_shift_toggle"
        config = KeyboardConfig.from_subiquity_kb_model(kb)
        self.assertEqual(config.model, "pc105")
        self.assertEqual(config.layout, "us")
        self.assertEqual(config.variant, "")
        self.assertEqual(config.options, ["grp:alt_shift_toggle"])
