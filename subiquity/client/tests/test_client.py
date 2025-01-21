# Copyright 2025 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from unittest.mock import Mock

from subiquity.client.client import SubiquityClient
from subiquitycore.tests import SubiTestCase


class TestClientVariantSupport(SubiTestCase):
    async def asyncSetUp(self):
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tmp_dir()
        opts.machine_config = "examples/machines/simple.json"
        opts.answers = None
        self.client = SubiquityClient(opts, None)
        self.client.make_apport_report = Mock()

    def test_default_variant(self):
        expected = SubiquityClient.variant_to_controllers["server"]
        self.assertEqual(
            # The controllers attribute is a list of names before init
            SubiquityClient.controllers,
            expected,
            "default controller names do not match names for 'server' variant",
        )
        self.assertEqual(
            # The controllers attribute is a ControllerSet after init
            self.client.controllers.controller_names,
            expected,
            "controllers changed unexpectedly during init",
        )
