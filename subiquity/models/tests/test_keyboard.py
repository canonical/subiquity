# Copyright 2022 Canonical, Ltd.
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

from subiquity.common.types import KeyboardSetting
from subiquity.models.keyboard import InconsistentMultiLayoutError, KeyboardModel
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.parameterized import parameterized


class TestKeyboardModel(SubiTestCase):
    def setUp(self):
        self.model = KeyboardModel(self.tmp_dir())

    def testDefaultUS(self):
        self.assertIsNone(self.model._setting)
        self.assertEqual("us", self.model.setting.layout)

    @parameterized.expand((["zz"], ["en"]))
    def testSetToInvalidLayout(self, layout):
        initial = self.model.setting
        val = KeyboardSetting(layout=layout)
        with self.assertRaises(ValueError):
            self.model.setting = val
        self.assertEqual(initial, self.model.setting)

    @parameterized.expand((["zz"]))
    def testSetToInvalidVariant(self, variant):
        initial = self.model.setting
        val = KeyboardSetting(layout="us", variant=variant)
        with self.assertRaises(ValueError):
            self.model.setting = val
        self.assertEqual(initial, self.model.setting)

    def testMultiLayout(self):
        val = KeyboardSetting(layout="us,ara", variant=",")
        self.model.setting = val
        self.assertEqual(self.model.setting, val)

    def testInconsistentMultiLayout(self):
        initial = self.model.setting
        val = KeyboardSetting(layout="us,ara", variant="")
        with self.assertRaises(InconsistentMultiLayoutError):
            self.model.setting = val
        self.assertEqual(self.model.setting, initial)

    def testInvalidMultiLayout(self):
        initial = self.model.setting
        val = KeyboardSetting(layout="us,ara", variant="zz,")
        with self.assertRaises(ValueError):
            self.model.setting = val
        self.assertEqual(self.model.setting, initial)

    @parameterized.expand(
        [
            ["ast_ES.UTF-8", "es", "ast"],
            ["de_DE.UTF-8", "de", ""],
            ["fr_FR.UTF-8", "fr", "latin9"],
            ["oc", "us", ""],
        ]
    )
    def testSettingForLang(self, lang, layout, variant):
        val = self.model.setting_for_lang(lang)
        self.assertEqual(layout, val.layout)
        self.assertEqual(variant, val.variant)

    def testAllLangsHaveKeyboardSuggestion(self):
        # every language in the list needs a suggestion,
        # even if only the default
        with open("languagelist") as fp:
            for line in fp.readlines():
                tokens = line.split(":")
                locale = tokens[1]
                self.assertIn(locale, self.model.layout_for_lang.keys())

    def testLoadSuggestions(self):
        data = self.tmp_path("kbd.yaml")
        with open(data, "w") as fp:
            fp.write(
                """
aa_BB.UTF-8:
  layout: aa
  variant: cc
"""
            )
        actual = self.model.load_layout_suggestions(data)
        expected = {"aa_BB.UTF-8": KeyboardSetting(layout="aa", variant="cc")}
        self.assertEqual(expected, actual)
