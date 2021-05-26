# Copyright 2020-2021 Canonical, Ltd.
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

import mock
from subiquitycore.context import Context
from subiquitycore.pubsub import MessageHub


class MockedApplication:
    signal = loop = None
    project = "mini"
    autoinstall_config = {}
    answers = {}
    opts = None


def make_app(model=None):
    app = MockedApplication()
    app.ui = mock.Mock()
    if model is not None:
        app.base_model = model
    else:
        app.base_model = mock.Mock()
    app.context = Context.new(app)
    app.exit = mock.Mock()
    app.respond = mock.Mock()
    app.next_screen = mock.Mock()
    app.prev_screen = mock.Mock()
    app.hub = MessageHub()
    return app
