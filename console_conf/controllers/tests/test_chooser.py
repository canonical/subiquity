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
from unittest import mock

from subiquitycore.context import Context
from console_conf.controllers.chooser import (
    RecoveryChooserController,
    RecoveryChooserConfirmController,
    )
from console_conf.models.systems import (
    RecoverySystemsModel,
    SelectedSystemAction,
    )


class MockedApplication:
    signal = loop = None
    project = "mini"
    autoinstall_config = {}
    answers = {}
    opts = None


def make_app():
    app = MockedApplication()
    app.ui = mock.Mock()
    app.base_model = mock.Mock()
    app.context = Context.new(app)
    app.exit = mock.Mock()
    app.respond = mock.Mock()
    app.next_screen = mock.Mock()
    return app


model1_non_current = {
    "current": False,
    "label": "1234",
    "brand": {
        "display-name": "brand 1",
        "username": "brand-1",
        "id": "brand-1-id",
        "validation": "certified",
    },
    "model": {
        "display-name": "model 1",
        "brand-id": "brand-1",
        "model": "model-1",
    },
    "actions": [
        {"title": "action 1", "mode": "action1"},
        {"title": "action 2", "mode": "action2"},
    ]
}

model2_current = {
    "current": True,
    "label": "other-label",
    "brand": {
        "display-name": "brand 2",
        "username": "brand-2",
        "id": "brand-2-id",
        "validation": "unproven",
    },
    "model": {
        "display-name": "model 2",
        "brand-id": "brand-2",
        "model": "model-2",
    },
    "actions": [
        {"title": "action 1", "mode": "action1"},
    ]
}


def make_model():
    return RecoverySystemsModel.from_systems([model1_non_current,
                                              model2_current])


class TestChooserConfirmController(unittest.TestCase):

    def test_abort(self):
        app = make_app()
        c = RecoveryChooserConfirmController(app)
        c.cancel()
        app.respond.assert_not_called()
        app.exit.assert_called()

    def test_confirm(self):
        app = make_app()
        c = RecoveryChooserConfirmController(app)
        c.model = mock.Mock(selection='selection')
        c.confirm()
        app.respond.assert_called_with('selection')
        app.exit.assert_called()

    @mock.patch('console_conf.controllers.chooser.ChooserConfirmView')
    def test_confirm_view(self, ccv):
        app = make_app()
        c = RecoveryChooserConfirmController(app)
        c.model = make_model()
        c.model.select(c.model.systems[0], c.model.systems[0].actions[0])
        c.start_ui()
        ccv.assert_called()


class TestChooserController(unittest.TestCase):

    def test_abort(self):
        app = make_app()
        c = RecoveryChooserController(app)
        c.cancel()
        app.respond.assert_not_called()
        app.exit.assert_called()

    def test_select(self):
        app = make_app()
        c = RecoveryChooserController(app)
        c.model = make_model()

        c.select(c.model.systems[0], c.model.systems[0].actions[0])
        exp = SelectedSystemAction(system=c.model.systems[0],
                                   action=c.model.systems[0].actions[0])
        self.assertEqual(c.model.selection, exp)

        app.next_screen.assert_called()
        app.respond.assert_not_called()
        app.exit.assert_not_called()

    @mock.patch('console_conf.controllers.chooser.ChooserCurrentSystemView')
    @mock.patch('console_conf.controllers.chooser.ChooserView')
    def test_current_ui_first(self, cv, ccsv):
        app = make_app()
        c = RecoveryChooserController(app)
        c.model = make_model()

        c.start_ui()
        # current system view is constructed
        ccsv.assert_called_with(c, c.model.current, has_more=True)
        # but the all systems view is not
        cv.assert_not_called()
        ccsv.reset_mock()
        # user selects more options and the view is replaced
        c.more_options()
        # we get the all systems view now
        cv.assert_called_with(c, c.model.systems)
        # and the current system view was not constructed
        ccsv.assert_not_called()

    @mock.patch('console_conf.controllers.chooser.ChooserCurrentSystemView')
    @mock.patch('console_conf.controllers.chooser.ChooserView')
    def test_only_one_and_current(self, cv, ccsv):
        app = make_app()
        c = RecoveryChooserController(app)
        c.model = RecoverySystemsModel.from_systems([model2_current])

        c.start_ui()
        # current system view is constructed
        ccsv.assert_called_with(c, c.model.current, has_more=False)
        # but the all systems view is not
        cv.assert_not_called()

    @mock.patch('console_conf.controllers.chooser.ChooserCurrentSystemView')
    @mock.patch('console_conf.controllers.chooser.ChooserView')
    def test_all_systems_first_no_current(self, cv, ccsv):
        app = make_app()
        c = RecoveryChooserController(app)
        c.model = RecoverySystemsModel.from_systems([model1_non_current])
        # sanity
        self.assertIsNone(c.model.current)

        c.start_ui()
        # we get the all systems view now
        cv.assert_called()
        # current system view is not constructed
        ccsv.assert_not_called()
