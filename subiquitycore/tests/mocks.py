# Copyright 2020-2021 Canonical, Ltd.
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
from unittest import mock

from subiquitycore.context import Context
from subiquitycore.pubsub import MessageHub


class MockedApplication:
    signal = loop = None
    project = "mini"
    autoinstall_config = {}
    answers = {}
    opts = None

    def make_autoinstall(self):
        return {"mock_key": "mock_data"}


def make_app(model=None):
    app = MockedApplication()
    app.ui = mock.Mock()
    if model is not None:
        app.base_model = model
    else:
        app.base_model = mock.Mock()
    app.add_event_listener = mock.Mock()
    app.controllers = mock.Mock()
    app.context = Context.new(app)
    app.exit = mock.Mock()
    app.respond = mock.Mock()
    app.request_next_screen = mock.Mock()
    app.request_prev_screen = mock.Mock()
    app.hub = MessageHub()
    app.opts = mock.Mock()
    app.opts.dry_run = True
    app.scale_factor = 1000
    app.echo_syslog_id = None
    app.log_syslog_id = None
    app.report_start_event = mock.Mock()
    app.report_finish_event = mock.Mock()
    app.make_apport_report = mock.Mock()
    app.snapdapi = mock.AsyncMock()

    return app
