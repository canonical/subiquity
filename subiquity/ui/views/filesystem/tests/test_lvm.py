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
from unittest import mock

import urwid

from subiquitycore.testing import view_helpers
from subiquitycore.view import BaseView

from subiquity.client.controllers.filesystem import FilesystemController
from subiquity.ui.views.filesystem.lvm import VolGroupStretchy
from subiquity.ui.views.filesystem.tests.test_partition import (
    make_model_and_disk,
    )


def make_view(model, existing=None):
    controller = mock.create_autospec(spec=FilesystemController)
    base_view = BaseView(urwid.Text(""))
    base_view.model = model
    base_view.controller = controller
    base_view.refresh_model_inputs = lambda: None
    stretchy = VolGroupStretchy(base_view, existing)
    base_view.show_stretchy_overlay(stretchy)
    return base_view, stretchy


class LVMViewTests(unittest.TestCase):

    def test_create_vg(self):
        model, disk = make_model_and_disk()
        part1 = model.add_partition(disk, 10*(2**30))
        part2 = model.add_partition(disk, 10*(2**30))
        view, stretchy = make_view(model)
        form_data = {
            'name': 'vg1',
            'devices': {part1: 'active', part2: 'active'},
            }
        expected_data = {
            'name': 'vg1',
            'devices': {part1, part2},
            'encrypt': False,
            }
        view_helpers.enter_data(stretchy.form, form_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        view.controller.volgroup_handler.assert_called_once_with(
            None, expected_data)

    def test_create_vg_encrypted(self):
        model, disk = make_model_and_disk()
        part1 = model.add_partition(disk, 10*(2**30))
        part2 = model.add_partition(disk, 10*(2**30))
        view, stretchy = make_view(model)
        form_data = {
            'name': 'vg1',
            'devices': {part1: 'active', part2: 'active'},
            'encrypt': True,
            'password': 'passw0rd',
            'confirm_password': 'passw0rd',
            }
        expected_data = {
            'name': 'vg1',
            'devices': {part1, part2},
            'encrypt': True,
            'password': 'passw0rd',
            }
        view_helpers.enter_data(stretchy.form, form_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        view.controller.volgroup_handler.assert_called_once_with(
            None, expected_data)
