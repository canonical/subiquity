# Copyright 2022 Canonical, Ltd.
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

from unittest import mock, TestCase

from subiquity.server.controllers.filesystem import FilesystemController

from subiquitycore.tests.util import run_coro
from subiquitycore.tests.mocks import make_app


class TestSubiquityControllerFilesystem(TestCase):
    def setUp(self):
        self.app = make_app()
        self.app.opts.bootloader = 'UEFI'
        self.app.report_start_event = mock.Mock()
        self.app.report_finish_event = mock.Mock()
        self.app.prober = mock.Mock()
        self.fsc = FilesystemController(app=self.app)
        self.fsc._configured = True

    def test_probe_restricted(self):
        run_coro(self.fsc._probe_once(context=None, restricted=True))
        self.app.prober.get_storage.assert_called_with({'blockdev'})

    def test_probe_defaults(self):
        self.app.opts.use_os_prober = False
        run_coro(self.fsc._probe_once(context=None, restricted=False))
        self.app.prober.get_storage.assert_called_with({'defaults'})

    def test_probe_defaults_and_os(self):
        self.app.opts.use_os_prober = True
        run_coro(self.fsc._probe_once(context=None, restricted=False))
        self.app.prober.get_storage.assert_called_with({'defaults', 'os'})
