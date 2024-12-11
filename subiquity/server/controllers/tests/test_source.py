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

import unittest

from subiquity.common.serialize import Serializer
from subiquity.models.source import CatalogEntry
from subiquity.models.subiquity import SubiquityModel
from subiquity.models.tests.test_source import make_entry as make_raw_entry
from subiquity.server.controllers.source import SourceController, convert_source
from subiquity.server.server import INSTALL_MODEL_NAMES, POSTINSTALL_MODEL_NAMES
from subiquitycore.pubsub import MessageHub
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.parameterized import parameterized


def make_entry(**kw):
    return Serializer().deserialize(CatalogEntry, make_raw_entry(**kw))


class TestSubiquityModel(unittest.TestCase):
    def test_convert_source(self):
        entry = make_entry()
        source = convert_source(entry, "C")
        self.assertEqual(source.id, entry.id)

    def test_convert_translations(self):
        entry = make_entry(
            name={
                "en": "English",
                "fr": "French",
                "fr_CA": "French Canadian",
            }
        )
        self.assertEqual(convert_source(entry, "C").name, "English")
        self.assertEqual(convert_source(entry, "en").name, "English")
        self.assertEqual(convert_source(entry, "fr").name, "French")
        self.assertEqual(convert_source(entry, "fr_CA").name, "French Canadian")
        self.assertEqual(convert_source(entry, "fr_BE").name, "French")


class TestSourceController(SubiTestCase):
    def setUp(self):
        self.base_model = SubiquityModel(
            "test", MessageHub(), INSTALL_MODEL_NAMES, POSTINSTALL_MODEL_NAMES
        )
        self.app = make_app(model=self.base_model)
        self.app.opts.source_catalog = "examples/sources/install.yaml"
        self.controller = SourceController(self.app)

    def _set_source_catalog(self, path):
        self.app.opts.source_catalog = path
        self.controller = SourceController(self.app)

    @parameterized.expand(
        #   (Sources list, is_desktop)
        (
            ("examples/sources/desktop.yaml", "desktop"),
            ("examples/sources/install.yaml", "server"),
        )
    )
    def test_install_source_detection__defaults(self, catalog, expected):
        """Test source detection with defaults."""

        self._set_source_catalog(catalog)

        variant = self.controller.model.current.variant
        self.assertEqual(variant, expected)

    @parameterized.expand(
        #   (Sources list, ai_data, expected)
        (
            ("examples/sources/mixed.yaml", {"id": "ubuntu-desktop"}, "desktop"),
            ("examples/sources/mixed.yaml", {"id": "ubuntu-server"}, "server"),
        )
    )
    def test_install_source_detection__autoinstall(self, catalog, ai_data, expected):
        """Test source detection with autoinstall."""
        self._set_source_catalog(catalog)
        self.controller.load_autoinstall_data(ai_data)
        self.assertEqual(self.controller.model.current.variant, expected)

    async def test_on_configure_update_variant(self):
        """Test update variant through server on configure.

        Ensure the source controller doesn't update variant on the base
        model directly.
        """
        app = self.controller.app = unittest.mock.Mock()
        model = self.controller.app.base_model = unittest.mock.Mock()

        self.controller.model.current.variant = "mock-variant"

        with unittest.mock.patch(
            "subiquity.server.controller.SubiquityController.configured"
        ):
            await self.controller.configured()

        app.set_source_variant.assert_called_with("mock-variant")
        model.set_source_variant.assert_not_called()
