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

from subiquity.models.mirror import (
    countrify_uri,
    MirrorModel,
    )


class TestCountrifyUrl(unittest.TestCase):
    def test_official_archive(self):
        self.assertEqual(
                countrify_uri(
                    "http://archive.ubuntu.com/ubuntu",
                    cc="fr"),
                "http://fr.archive.ubuntu.com/ubuntu")

        self.assertEqual(
                countrify_uri(
                    "http://archive.ubuntu.com/ubuntu",
                    cc="us"),
                "http://us.archive.ubuntu.com/ubuntu")

    def test_ports_archive(self):
        self.assertEqual(
                countrify_uri(
                    "http://ports.ubuntu.com/ubuntu-ports",
                    cc="fr"),
                "http://fr.ports.ubuntu.com/ubuntu-ports")

        self.assertEqual(
                countrify_uri(
                    "http://ports.ubuntu.com/ubuntu-ports",
                    cc="us"),
                "http://us.ports.ubuntu.com/ubuntu-ports")


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
        config = self.model.get_apt_config_staged()
        self.assertEqual([], config['disable_components'])

    def test_from_autoinstall(self):
        # autoinstall loads to the config directly
        data = {'disable_components': ['non-free']}
        self.model.load_autoinstall_data(data)
        config = self.model.get_apt_config_staged()
        self.assertEqual(['non-free'], config['disable_components'])

    def test_disable_add(self):
        expected = ['things', 'stuff']
        self.model.disable_components(expected.copy(), add=True)
        actual = self.model.get_apt_config_staged()['disable_components']
        actual.sort()
        expected.sort()
        self.assertEqual(expected, actual)

    def test_disable_remove(self):
        self.model.disabled_components = set(['a', 'b', 'things'])
        to_remove = ['things', 'stuff']
        expected = ['a', 'b']
        self.model.disable_components(to_remove, add=False)
        actual = self.model.get_apt_config_staged()['disable_components']
        actual.sort()
        expected.sort()
        self.assertEqual(expected, actual)

    def test_make_autoinstall(self):
        primary = [{"arches": "amd64", "uri": "http://mirror"}]
        self.model.disabled_components = set(["non-free"])
        self.model.primary_candidates = [primary]
        self.model.primary_elected = primary
        cfg = self.model.make_autoinstall()
        self.assertEqual(cfg["disable_components"], ["non-free"])
        self.assertEqual(cfg["primary"], primary)
