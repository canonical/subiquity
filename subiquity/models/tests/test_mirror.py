# Copyright 2019 Canonical, Ltd.
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

import unittest

from curtin.config import merge_config

from subiquity.models.mirror import (
    MirrorModel,
    )


class TestMirrorModel(unittest.TestCase):
    def setUp(self):
        self.model = MirrorModel()

    def test_set_country(self):
        self.model.set_country("CC")
        self.assertIn(
            self.model.get_mirror(),
            [
                "http://CC.archive.ubuntu.com/ubuntu",
                "http://CC.ports.ubuntu.com/ubuntu-ports",
            ])

    def test_set_mirror(self):
        self.model.set_mirror("http://mymirror.invalid/")
        self.assertEqual(self.model.get_mirror(), "http://mymirror.invalid/")

    def test_set_country_after_set_mirror(self):
        self.model.set_mirror("http://mymirror.invalid/")
        self.model.set_country("CC")
        self.assertEqual(self.model.get_mirror(), "http://mymirror.invalid/")

    def test_default_disable_components(self):
        config = self.model.get_apt_config()
        self.assertEqual([], config['disable_components'])

    def test_from_autoinstall(self):
        # autoinstall loads to the config directly
        data = {'disable_components': ['non-free']}
        merge_config(self.model.config, data)
        config = self.model.get_apt_config()
        self.assertEqual(['non-free'], config['disable_components'])

    def test_disable_add(self):
        expected = ['things', 'stuff']
        self.model.disable_components(expected.copy(), add=True)
        actual = self.model.get_apt_config()['disable_components']
        actual.sort()
        expected.sort()
        self.assertEqual(expected, actual)

    def test_disable_remove(self):
        self.model.config['disable_components'] = ['a', 'b', 'things']
        to_remove = ['things', 'stuff']
        expected = ['a', 'b']
        self.model.disable_components(to_remove, add=False)
        actual = self.model.get_apt_config()['disable_components']
        actual.sort()
        expected.sort()
        self.assertEqual(expected, actual)
