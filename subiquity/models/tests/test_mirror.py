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
    DEFAULT_PRIMARY_SECTION,
    MirrorModel,
    PrimarySection,
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


class TestPrimarySection(unittest.TestCase):
    def setUp(self):
        self.model = MirrorModel()

    def test_initializer(self):
        primary = PrimarySection([], parent=self.model)
        self.assertEqual(primary.config, [])
        self.assertEqual(primary.parent, self.model)

    def test_new_from_default(self):
        primary = PrimarySection.new_from_default(parent=self.model)
        self.assertEqual(primary.config, DEFAULT_PRIMARY_SECTION)

    def test_get_uri(self):
        self.model.architecture = "amd64"
        primary = PrimarySection([{"uri": "http://myurl", "arches": "amd64"}],
                                 parent=self.model)
        self.assertEqual(primary.uri, "http://myurl")

    def test_set_uri(self):
        primary = PrimarySection.new_from_default(parent=self.model)
        primary.uri = "http://mymirror.invalid/"
        self.assertEqual(primary.uri, "http://mymirror.invalid/")


class TestMirrorModel(unittest.TestCase):
    def setUp(self):
        self.model = MirrorModel()
        self.candidate = self.model.primary_candidates[0]
        self.model.primary_staged = self.candidate

    def test_set_country(self):
        self.model.set_country("CC")
        self.assertIn(
            self.candidate.uri,
            [
                "http://CC.archive.ubuntu.com/ubuntu",
                "http://CC.ports.ubuntu.com/ubuntu-ports",
            ])

    def test_set_country_after_set_uri(self):
        candidate = self.model.primary_candidates[0]
        candidate.uri = "http://mymirror.invalid/"
        self.model.set_country("CC")
        self.assertEqual(candidate.uri, "http://mymirror.invalid/")

    def test_default_disable_components(self):
        config = self.model.get_apt_config_staged()
        self.assertEqual([], config['disable_components'])

    def test_from_autoinstall(self):
        # autoinstall loads to the config directly
        data = {'disable_components': ['non-free']}
        self.model.load_autoinstall_data(data)
        self.candidate = self.model.primary_candidates[0]
        self.model.primary_staged = self.candidate
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
        self.model.primary_candidates = \
            [PrimarySection(primary, parent=self.model)]
        self.model.primary_elected = self.model.primary_candidates[0]
        cfg = self.model.make_autoinstall()
        self.assertEqual(cfg["disable_components"], ["non-free"])
        self.assertEqual(cfg["primary"], primary)

    def test_replace_primary_candidates(self):
        self.model.replace_primary_candidates(["http://single-valid"])
        self.assertEqual(len(self.model.primary_candidates), 1)
        self.assertEqual(self.model.primary_candidates[0].uri,
                         "http://single-valid")

        self.model.replace_primary_candidates(
                ["http://valid1", "http://valid2"])
        self.assertEqual(len(self.model.primary_candidates), 2)
        self.assertEqual(self.model.primary_candidates[0].uri,
                         "http://valid1")
        self.assertEqual(self.model.primary_candidates[1].uri,
                         "http://valid2")

    def test_assign_primary_elected(self):
        self.model.assign_primary_elected("http://mymirror.valid")
        self.assertEqual(self.model.primary_elected.uri,
                         "http://mymirror.valid")
