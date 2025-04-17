# Copyright 2025 Canonical, Ltd.
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
from unittest.mock import patch

from subiquity.common.types.storage import Disk
from subiquity.ui.views.filesystem.guided import summarize_device


class TestGuidedSummarizeDevice(unittest.TestCase):
    def test_install_media(self):
        d = Disk(
            id="disk-vda",
            label="My disk",
            type="local disk",
            size=1 << 30,
            usage_labels=["already formatted as iso9660", "in use"],
            partitions=[],
            ok_for_guided=True,
            ptable="gpt",
            preserve=True,
            path="/dev/vda",
            boot_device=False,
            can_be_boot_device=True,
            has_in_use_partition=True,
        )

        # In urwid, comparing two Text instances evaluates to false even if the
        # content is the same.
        # urwid.Text("foo") != urwid.Text("foo")
        # Let's define a function that will return True if args are the same.
        def noop(*args, **kwargs):
            return *args, dict(**kwargs)

        Text = noop
        # Also urwid will be unhappy if we don't pass a real Text instance to
        # info_minor, so mock it as well.
        info_minor = noop

        p_text = patch("subiquity.ui.views.filesystem.guided.Text", side_effect=Text)
        p_info_minor = patch(
            "subiquity.ui.views.filesystem.guided.Color.info_minor",
            side_effect=info_minor,
        )

        with p_text as m_text, p_info_minor as m_info_minor:
            row_disk, row_usage_labels = summarize_device(d)

        self.assertIsNone(row_disk[0])
        self.assertEqual(row_disk[1][0], (2, Text("My disk")))
        self.assertEqual(row_disk[1][1], Text("local disk"))
        self.assertEqual(row_disk[1][2], Text("1.000G", align="right"))

        self.assertIsNone(row_usage_labels[0])
        self.assertEqual(
            row_usage_labels[1][0],
            (4, info_minor(Text("already formatted as iso9660, in use"))),
        )

        m_text.assert_called()
        m_info_minor.assert_called_once()
