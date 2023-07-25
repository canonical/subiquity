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

from subiquitycore.prober import Prober
from subiquitycore.tests import SubiTestCase


class TestProber(SubiTestCase):
    async def test_none_and_defaults_equal(self):
        with open("examples/machines/simple.json", "r") as fp:
            prober = Prober(machine_config=fp, debug_flags=())
        none_storage = await prober.get_storage(probe_types=None)
        defaults_storage = await prober.get_storage(probe_types={"defaults"})
        self.assertEqual(defaults_storage, none_storage)
