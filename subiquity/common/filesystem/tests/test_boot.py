# Copyright 2024 Canonical, Ltd.
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
from unittest.mock import Mock

import attr

from subiquity.common.filesystem.boot import (
    CreatePartPlan,
    MountBootEfiPlan,
    MultiStepPlan,
    NoOpBootPlan,
    ResizePlan,
    SetAttrPlan,
    SlidePlan,
)


class TestMakeBootDevicePlan(unittest.TestCase):
    @unittest.skipUnless(
        hasattr(attr.validators, "disabled"),
        "this test requires attr.validators.disabled context manager",
    )
    def test_new_partition_count__single(self):
        self.assertEqual(1, CreatePartPlan(Mock()).new_partition_count())
        with attr.validators.disabled():
            self.assertEqual(0, ResizePlan(Mock()).new_partition_count())
        with attr.validators.disabled():
            self.assertEqual(0, SlidePlan(Mock()).new_partition_count())
        self.assertEqual(0, SetAttrPlan(Mock(), Mock(), Mock()).new_partition_count())
        self.assertEqual(0, MountBootEfiPlan(Mock()).new_partition_count())
        self.assertEqual(0, NoOpBootPlan().new_partition_count())

    def test_new_partition_count__multi_step(self):
        self.assertEqual(0, MultiStepPlan([]).new_partition_count())

        self.assertEqual(
            3,
            MultiStepPlan(
                [
                    CreatePartPlan(Mock()),
                    CreatePartPlan(Mock()),
                    CreatePartPlan(Mock()),
                ]
            ).new_partition_count(),
        )

        self.assertEqual(
            2,
            MultiStepPlan(
                [
                    CreatePartPlan(Mock()),
                    CreatePartPlan(Mock()),
                    MountBootEfiPlan(Mock()),
                    NoOpBootPlan(),
                ]
            ).new_partition_count(),
        )
