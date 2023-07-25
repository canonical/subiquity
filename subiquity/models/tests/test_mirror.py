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

import copy
import unittest
from unittest import mock

from subiquity.models.mirror import (
    LEGACY_DEFAULT_PRIMARY_SECTION,
    LegacyPrimaryEntry,
    MirrorModel,
    MirrorSelectionFallback,
    PrimaryEntry,
    countrify_uri,
)


class TestCountrifyUrl(unittest.TestCase):
    def test_official_archive(self):
        self.assertEqual(
            countrify_uri("http://archive.ubuntu.com/ubuntu", cc="fr"),
            "http://fr.archive.ubuntu.com/ubuntu",
        )

        self.assertEqual(
            countrify_uri("http://archive.ubuntu.com/ubuntu", cc="us"),
            "http://us.archive.ubuntu.com/ubuntu",
        )

    def test_ports_archive(self):
        self.assertEqual(
            countrify_uri("http://ports.ubuntu.com/ubuntu-ports", cc="fr"),
            "http://fr.ports.ubuntu.com/ubuntu-ports",
        )

        self.assertEqual(
            countrify_uri("http://ports.ubuntu.com/ubuntu-ports", cc="us"),
            "http://us.ports.ubuntu.com/ubuntu-ports",
        )


class TestPrimaryEntry(unittest.TestCase):
    def test_initializer(self):
        model = MirrorModel()

        entry = PrimaryEntry(parent=model)
        self.assertEqual(entry.parent, model)
        self.assertIsNone(entry.uri, None)
        self.assertIsNone(entry.arches, None)

        entry = PrimaryEntry("http://mirror", ["amd64"], parent=model)
        self.assertEqual(entry.parent, model)
        self.assertEqual(entry.uri, "http://mirror")
        self.assertEqual(entry.arches, ["amd64"])

        entry = PrimaryEntry(uri="http://mirror", arches=[], parent=model)
        self.assertEqual(entry.parent, model)
        self.assertEqual(entry.uri, "http://mirror")
        self.assertEqual(entry.arches, [])

    def test_from_config(self):
        model = MirrorModel()

        entry = PrimaryEntry.from_config("country-mirror", parent=model)
        self.assertEqual(entry, PrimaryEntry(parent=model, country_mirror=True))

        with self.assertRaises(ValueError):
            entry = PrimaryEntry.from_config({}, parent=model)

        entry = PrimaryEntry.from_config({"uri": "http://mirror"}, parent=model)
        self.assertEqual(entry, PrimaryEntry(uri="http://mirror", parent=model))

        entry = PrimaryEntry.from_config(
            {"uri": "http://mirror", "arches": ["amd64"]}, parent=model
        )
        self.assertEqual(
            entry, PrimaryEntry(uri="http://mirror", arches=["amd64"], parent=model)
        )


class TestLegacyPrimaryEntry(unittest.TestCase):
    def setUp(self):
        self.model = MirrorModel()

    def test_initializer(self):
        primary = LegacyPrimaryEntry([], parent=self.model)
        self.assertEqual(primary.config, [])
        self.assertEqual(primary.parent, self.model)

    def test_new_from_default(self):
        primary = LegacyPrimaryEntry.new_from_default(parent=self.model)
        self.assertEqual(primary.config, LEGACY_DEFAULT_PRIMARY_SECTION)

    def test_get_uri(self):
        self.model.architecture = "amd64"
        primary = LegacyPrimaryEntry(
            [{"uri": "http://myurl", "arches": "amd64"}], parent=self.model
        )
        self.assertEqual(primary.uri, "http://myurl")

    def test_set_uri(self):
        primary = LegacyPrimaryEntry.new_from_default(parent=self.model)
        primary.uri = "http://mymirror.invalid/"
        self.assertEqual(primary.uri, "http://mymirror.invalid/")


class TestMirrorModel(unittest.TestCase):
    def setUp(self):
        self.model = MirrorModel()
        self.candidate = self.model.primary_candidates[1]
        self.candidate.stage()

        self.model_legacy = MirrorModel()
        self.model_legacy.legacy_primary = True
        self.model_legacy.primary_candidates = [
            LegacyPrimaryEntry(
                copy.deepcopy(LEGACY_DEFAULT_PRIMARY_SECTION), parent=self.model_legacy
            ),
        ]
        self.candidate_legacy = self.model_legacy.primary_candidates[0]
        self.model_legacy.primary_staged = self.candidate_legacy

    def test_initializer(self):
        model = MirrorModel()
        self.assertFalse(model.legacy_primary)
        self.assertIsNone(model.primary_staged)

    def test_set_country(self):
        def do_test(model):
            country_mirror_candidates = list(model.country_mirror_candidates())
            self.assertEqual(len(country_mirror_candidates), 1)
            model.set_country("CC")
            for country_mirror_candidate in country_mirror_candidates:
                self.assertIn(
                    country_mirror_candidate.uri,
                    [
                        "http://CC.archive.ubuntu.com/ubuntu",
                        "http://CC.ports.ubuntu.com/ubuntu-ports",
                    ],
                )

        do_test(self.model)
        do_test(self.model_legacy)

    def test_set_country_after_set_uri_legacy(self):
        for candidate in self.model_legacy.primary_candidates:
            candidate.uri = "http://mymirror.invalid/"
        self.model_legacy.set_country("CC")
        for candidate in self.model_legacy.primary_candidates:
            self.assertEqual(candidate.uri, "http://mymirror.invalid/")

    def test_default_disable_components(self):
        def do_test(model, candidate):
            config = model.get_apt_config_staged()
            self.assertEqual([], config["disable_components"])

        # The candidate[0] is a country-mirror, skip it.
        candidate = self.model.primary_candidates[1]
        candidate.stage()
        do_test(self.model, candidate)
        do_test(self.model_legacy, self.candidate_legacy)

    def test_from_autoinstall_no_primary(self):
        # autoinstall loads to the config directly
        model = MirrorModel()
        data = {
            "disable_components": ["non-free"],
            "fallback": "offline-install",
        }
        model.load_autoinstall_data(data)
        self.assertFalse(model.legacy_primary)
        model.primary_candidates[0].stage()
        self.assertEqual(set(["non-free"]), model.disabled_components)
        self.assertEqual(model.primary_candidates, model._default_primary_entries())

    def test_from_autoinstall_modern(self):
        data = {
            "mirror-selection": {
                "primary": [
                    "country-mirror",
                    {
                        "uri": "http://mirror",
                    },
                ],
            }
        }
        model = MirrorModel()
        model.load_autoinstall_data(data)
        self.assertEqual(
            model.primary_candidates,
            [
                PrimaryEntry(parent=model, country_mirror=True),
                PrimaryEntry(uri="http://mirror", parent=model),
            ],
        )

    def test_disable_add(self):
        def do_test(model, candidate):
            expected = ["things", "stuff"]
            model.disable_components(expected.copy(), add=True)
            actual = model.get_apt_config_staged()["disable_components"]
            actual.sort()
            expected.sort()
            self.assertEqual(expected, actual)

        # The candidate[0] is a country-mirror, skip it.
        candidate = self.model.primary_candidates[1]
        candidate.stage()
        do_test(self.model, candidate)
        do_test(self.model_legacy, self.candidate_legacy)

    def test_disable_remove(self):
        self.model.disabled_components = set(["a", "b", "things"])
        to_remove = ["things", "stuff"]
        expected = ["a", "b"]
        self.model.disable_components(to_remove, add=False)
        actual = self.model.get_apt_config_staged()["disable_components"]
        actual.sort()
        expected.sort()
        self.assertEqual(expected, actual)

    def test_make_autoinstall_primary(self):
        expected_primary = [
            "country-mirror",
            {"uri": "http://mirror.local/ubuntu"},
            {"uri": "http://amd64.mirror.local/ubuntu", "arches": ["amd64"]},
        ]
        self.model.disabled_components = set(["non-free"])
        self.model.legacy_primary = False
        self.model.fallback = MirrorSelectionFallback.OFFLINE_INSTALL
        self.model.primary_candidates = [
            PrimaryEntry(uri=None, arches=None, country_mirror=True, parent=self.model),
            PrimaryEntry(
                uri="http://mirror.local/ubuntu", arches=None, parent=self.model
            ),
            PrimaryEntry(
                uri="http://amd64.mirror.local/ubuntu",
                arches=["amd64"],
                parent=self.model,
            ),
        ]
        cfg = self.model.make_autoinstall()
        self.assertEqual(cfg["disable_components"], ["non-free"])
        self.assertEqual(cfg["fallback"], "offline-install")
        self.assertEqual(cfg["mirror-selection"]["primary"], expected_primary)

    def test_make_autoinstall_legacy_primary(self):
        primary = [{"arches": "amd64", "uri": "http://mirror"}]
        self.model.disabled_components = set(["non-free"])
        self.model.fallback = MirrorSelectionFallback.ABORT
        self.model.legacy_primary = True
        self.model.primary_candidates = [LegacyPrimaryEntry(primary, parent=self.model)]
        self.model.primary_candidates[0].elect()
        cfg = self.model.make_autoinstall()
        self.assertEqual(cfg["disable_components"], ["non-free"])
        self.assertEqual(cfg["fallback"], "abort")
        self.assertEqual(cfg["primary"], primary)

    def test_create_primary_candidate(self):
        self.model.legacy_primary = False
        candidate = self.model.create_primary_candidate("http://mymirror.valid")
        self.assertEqual(candidate.uri, "http://mymirror.valid")
        self.model.legacy_primary = True
        candidate = self.model.create_primary_candidate("http://mymirror.valid")
        self.assertEqual(candidate.uri, "http://mymirror.valid")

    def test_wants_geoip(self):
        country_mirror_candidates = mock.patch.object(
            self.model, "country_mirror_candidates", return_value=iter([])
        )
        with country_mirror_candidates:
            self.assertFalse(self.model.wants_geoip())

        country_mirror_candidates = mock.patch.object(
            self.model,
            "country_mirror_candidates",
            return_value=iter([PrimaryEntry(parent=self.model)]),
        )
        with country_mirror_candidates:
            self.assertTrue(self.model.wants_geoip())
