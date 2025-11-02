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

import unittest

from subiquity.models.identity import DefaultGroups, User


class TestUser(unittest.TestCase):
    def test_from_autoinstall(self):
        data = {
            "username": "user1",
            "password": "$6$xxx",
            "realname": "My user",
        }
        user = User.from_autoinstall(data)

        self.assertEqual("user1", user.username)
        self.assertEqual("$6$xxx", user.password)
        self.assertEqual("My user", user.realname)
        self.assertEqual({DefaultGroups}, user.groups)

    def test_from_autoinstall__no_realname(self):
        data = {
            "username": "user1",
            "password": "$6$xxx",
        }
        user = User.from_autoinstall(data)

        self.assertEqual("user1", user.username)
        self.assertEqual("$6$xxx", user.password)
        self.assertEqual("", user.realname)
        self.assertEqual({DefaultGroups}, user.groups)

    def test_from_autoinstall__groups_override(self):
        data = {
            "username": "user1",
            "password": "$6$xxx",
            "groups": {"override": ["sudo", "lpadmin", "wheel"]},
        }
        user = User.from_autoinstall(data)

        self.assertEqual("user1", user.username)
        self.assertEqual("$6$xxx", user.password)
        self.assertEqual("", user.realname)
        self.assertEqual({"sudo", "lpadmin", "wheel"}, user.groups)

    def test_from_autoinstall__groups_override_syntactic_sugar(self):
        data = {
            "username": "user1",
            "password": "$6$xxx",
            "groups": ["sudo", "lpadmin", "wheel"],
        }
        user = User.from_autoinstall(data)

        self.assertEqual("user1", user.username)
        self.assertEqual("$6$xxx", user.password)
        self.assertEqual("", user.realname)
        self.assertEqual({"sudo", "lpadmin", "wheel"}, user.groups)

    def test_from_autoinstall__groups_add_extra(self):
        data = {
            "username": "user1",
            "password": "$6$xxx",
            "groups": {"append": ["sudo"]},
        }
        user = User.from_autoinstall(data)

        self.assertEqual("user1", user.username)
        self.assertEqual("$6$xxx", user.password)
        self.assertEqual("", user.realname)
        self.assertEqual({DefaultGroups, "sudo"}, user.groups)

    def test_to_autoinstall__default(self):
        user = User(
                username="user1",
                realname="my user",
                password="$6$xxxx",
                groups={DefaultGroups})

        self.assertEqual(
            {"username": "user1",
             "realname": "my user",
             "password": "$6$xxxx"}, user.to_autoinstall())

    def test_to_autoinstall__overridden_groups(self):
        user = User(
                username="user1",
                realname="my user",
                password="$6$xxxx",
                groups={"sudo", "lpadmin"})

        self.assertEqual(
            {"username": "user1",
             "realname": "my user",
             "password": "$6$xxxx",
             "groups": {"override": ["lpadmin", "sudo"]}}, user.to_autoinstall())

    def test_to_autoinstall__extra_groups(self):
        user = User(
                username="user1",
                realname="my user",
                password="$6$xxxx",
                groups={DefaultGroups, "sudo"})

        self.assertEqual(
            {"username": "user1",
             "realname": "my user",
             "password": "$6$xxxx",
             "groups": {"append": ["sudo"]}}, user.to_autoinstall())
