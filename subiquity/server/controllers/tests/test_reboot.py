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

from datetime import datetime
import sys

from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.tests.util import run_coro

from subiquity.common.types import ApplicationState
from subiquity.server.controllers.reboot import RebootController


# This feature is used with minimum python 3.8 / ubuntu-desktop-installer
if sys.version >= '3.7.0':
    class TestRebootController(SubiTestCase):

        # verify that POST returns before the reboot occurrs
        def test_reboot_event_order(self):
            async def passer():
                pass

            def now():
                nonlocal exited
                exited = datetime.now()

            async def poster():
                # There is a subtle timing difference between when
                # run_coro exits, and when the POST exits, which is
                # enough to skew results.
                nonlocal controller
                nonlocal returned
                rv = await controller.POST()
                returned = datetime.now()
                return rv

            for i in range(100):
                app = make_app()
                app.state = ApplicationState.DONE
                app.controllers.Install.install_task = passer()
                app.controllers.Late.run_event.wait = passer
                app.interactive = True
                app.exit.side_effect = now

                exited = None
                returned = None
                controller = RebootController(app)
                controller.start()
                app.exit.assert_not_called()
                rv = run_coro(poster(), 1)
                self.assertTrue(rv)
                app.exit.assert_called()
                self.assertTrue(returned < exited,
                                f'returned {returned} exited {exited}')
