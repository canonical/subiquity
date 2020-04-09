# Copyright 2020 Canonical, Ltd.
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

from console_conf.models.systems import (
    SystemAction,
    )
from console_conf.ui.views.chooser import (
    by_preferred_action_type,
    )


class TestSorting(unittest.TestCase):

    def test_simple(self):
        data = [
            SystemAction(title="b-other", mode="unknown"),
            SystemAction(title="reinstall", mode="install"),
            SystemAction(title="run normally", mode="run"),
            SystemAction(title="a-other", mode="some-other"),
            SystemAction(title="recover", mode="recover"),
        ]
        exp = [
            SystemAction(title="run normally", mode="run"),
            SystemAction(title="recover", mode="recover"),
            SystemAction(title="reinstall", mode="install"),
            SystemAction(title="a-other", mode="some-other"),
            SystemAction(title="b-other", mode="unknown"),
        ]
        self.assertSequenceEqual(sorted(data, key=by_preferred_action_type),
                                 exp)
