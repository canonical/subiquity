import unittest
from unittest import mock

import urwid

from subiquitycore.testing import view_helpers
from subiquitycore.view import BaseView

from subiquity.client.controllers.filesystem import FilesystemController
from subiquity.models.filesystem import (
    raidlevels_by_value,
    )
from subiquity.ui.views.filesystem.raid import RaidStretchy
from subiquity.ui.views.filesystem.tests.test_partition import (
    make_model_and_disk,
    )


def make_view(model, existing=None):
    controller = mock.create_autospec(spec=FilesystemController)
    base_view = BaseView(urwid.Text(""))
    base_view.model = model
    base_view.controller = controller
    base_view.refresh_model_inputs = lambda: None
    stretchy = RaidStretchy(base_view, existing)
    base_view.show_stretchy_overlay(stretchy)
    return base_view, stretchy


class RaidViewTests(unittest.TestCase):

    def test_create_raid(self):
        model, disk = make_model_and_disk()
        part1 = model.add_partition(disk, 10*(2**30))
        part2 = model.add_partition(disk, 10*(2**30))
        part3 = model.add_partition(disk, 10*(2**30))
        view, stretchy = make_view(model)
        form_data = {
            'name': 'md0',
            'devices': {part1: 'active', part2: 'active', part3: 'spare'},
            }
        expected_data = {
            'name': 'md0',
            'devices': {part1, part2},
            'spare_devices': {part3},
            'level': raidlevels_by_value["raid1"],
            }
        view_helpers.enter_data(stretchy.form, form_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        view.controller.raid_handler.assert_called_once_with(
            None, expected_data)

    def test_edit_raid(self):
        model, disk = make_model_and_disk()
        part1 = model.add_partition(disk, 10*(2**30))
        part2 = model.add_partition(disk, 10*(2**30))
        raid = model.add_raid("md0", "raid1", {part1, part2}, set())
        view, stretchy = make_view(model, raid)
        form_data = {
            'name': 'md1',
            'level': raidlevels_by_value["raid0"],
            }
        expected_data = {
            'name': 'md1',
            'devices': {part1, part2},
            'spare_devices': set(),
            'level': raidlevels_by_value["raid0"],
            }
        view_helpers.enter_data(stretchy.form, form_data)
        view_helpers.click(stretchy.form.done_btn.base_widget)
        view.controller.raid_handler.assert_called_once_with(
            raid, expected_data)
