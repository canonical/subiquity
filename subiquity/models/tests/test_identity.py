# Copyright 2026 Canonical, Ltd.
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

import unittest

from subiquity.models.identity import DefaultGroups, User


class TestUser(unittest.TestCase):
    def test_resolved_groups__default(self):
        """Test what happens when the user is created with default groups"""
        user = User(
            realname="my user",
            username="user",
            password="$6$x123",
            groups={DefaultGroups},
        )

        self.assertEqual(
            {"admin", "sudo"}, user.resolved_groups(default={"admin", "sudo"})
        )

    def test_resolved_groups__extra(self):
        """Test what happens if we have extra groups"""
        user = User(
            realname="my user",
            username="user",
            password="$6$x123",
            groups={"lpadmin", "wheel", DefaultGroups},
        )

        self.assertEqual(
            {"admin", "sudo", "lpadmin", "wheel"},
            user.resolved_groups(default={"admin", "sudo"}),
        )

    def test_resolved_groups__extra_redundant(self):
        """Test what happens if we specify extra groups that are already in the
        default groups"""
        user = User(
            realname="my user",
            username="user",
            password="$6$x123",
            groups={"sudo", DefaultGroups},
        )

        self.assertEqual(
            {"admin", "sudo"}, user.resolved_groups(default={"admin", "sudo"})
        )

    def test_resolved_groups__replaced(self):
        """Test what happens if we do not include the default groups"""
        user = User(
            realname="my user",
            username="user",
            password="$6$x123",
            groups={"wheel", "sudo"},
        )

        self.assertEqual(
            {"wheel", "sudo"}, user.resolved_groups(default={"admin", "sudo"})
        )
