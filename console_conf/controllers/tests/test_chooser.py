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

from subiquitycore.tests.mocks import make_app
from console_conf.controllers.chooser import (
    RecoveryChooserController,
    RecoveryChooserConfirmController,
    )
from console_conf.models.systems import (
    RecoverySystemsModel,
    SelectedSystemAction,
    )


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

    def test_back(self):
        app = make_app()
        c = RecoveryChooserConfirmController(app)
        c.model = mock.Mock(selection='selection')
        c.back()
        app.respond.assert_not_called()
        app.exit.assert_not_called()
        app.prev_screen.assert_called()
        c.model.unselect.assert_called()

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
        c.make_ui()
        ccv.assert_called()


class TestChooserController(unittest.TestCase):

    def test_select(self):
        app = make_app(model=make_model())
        c = RecoveryChooserController(app)

        c.select(c.model.systems[0], c.model.systems[0].actions[0])
        exp = SelectedSystemAction(system=c.model.systems[0],
                                   action=c.model.systems[0].actions[0])
        self.assertEqual(c.model.selection, exp)

        app.next_screen.assert_called()
        app.respond.assert_not_called()
        app.exit.assert_not_called()

    @mock.patch('console_conf.controllers.chooser.ChooserCurrentSystemView',
                return_value='current')
    @mock.patch('console_conf.controllers.chooser.ChooserView',
                return_value='all')
    def test_current_ui_first(self, cv, ccsv):
        app = make_app(model=make_model())
        c = RecoveryChooserController(app)
        # current system view is constructed
        ccsv.assert_called_with(c, c.model.current, has_more=True)
        # as well as all systems view
        cv.assert_called_with(c, c.model.systems)
        v = c.make_ui()
        self.assertEqual(v, 'current')
        # user selects more options and the view is replaced
        c.more_options()
        c.ui.set_body.assert_called_with('all')

    @mock.patch('console_conf.controllers.chooser.ChooserCurrentSystemView',
                return_value='current')
    @mock.patch('console_conf.controllers.chooser.ChooserView',
                return_value='all')
    def test_current_current_all_there_and_back(self, cv, ccsv):
        app = make_app(model=make_model())
        c = RecoveryChooserController(app)
        # sanity
        ccsv.assert_called_with(c, c.model.current, has_more=True)
        cv.assert_called_with(c, c.model.systems)

        v = c.make_ui()
        self.assertEqual(v, 'current')
        # user selects more options and the view is replaced
        c.more_options()
        c.ui.set_body.assert_called_with('all')
        # go back now
        c.back()
        c.ui.set_body.assert_called_with('current')
        # nothing
        c.back()
        c.ui.set_body.not_called()

    @mock.patch('console_conf.controllers.chooser.ChooserCurrentSystemView',
                return_value='current')
    @mock.patch('console_conf.controllers.chooser.ChooserView',
                return_value='all')
    def test_only_one_and_current(self, cv, ccsv):
        model = RecoverySystemsModel.from_systems([model2_current])
        app = make_app(model=model)
        c = RecoveryChooserController(app)
        # both views are constructed
        ccsv.assert_called_with(c, c.model.current, has_more=False)
        cv.assert_called_with(c, c.model.systems)

        v = c.make_ui()
        self.assertEqual(v, 'current')
        # going back does nothing
        c.back()
        c.ui.set_body.not_called()

    @mock.patch('console_conf.controllers.chooser.ChooserCurrentSystemView',
                return_value='current')
    @mock.patch('console_conf.controllers.chooser.ChooserView',
                return_value='all')
    def test_all_systems_first_no_current(self, cv, ccsv):
        model = RecoverySystemsModel.from_systems([model1_non_current])
        app = make_app(model=model)
        c = RecoveryChooserController(app)

        # sanity
        self.assertIsNone(c.model.current)

        # we get the all-systems view now
        cv.assert_called()
        # current system view is not constructed at all
        ccsv.assert_not_called()

        v = c.make_ui()
        self.assertEqual(v, 'all')
