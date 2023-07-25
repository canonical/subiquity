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

from unittest import mock

from subiquity.server import snapdapi
from subiquity.server.controllers import refresh as refresh_mod
from subiquity.server.controllers.refresh import RefreshController, SnapChannelSource
from subiquitycore.snapd import AsyncSnapd, get_fake_connection
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app


class TestRefreshController(SubiTestCase):
    def setUp(self):
        self.app = make_app()
        self.app.report_start_event = mock.Mock()
        self.app.report_finish_event = mock.Mock()
        self.app.note_data_for_apport = mock.Mock()
        self.app.prober = mock.Mock()
        self.app.snapdapi = snapdapi.make_api_client(AsyncSnapd(get_fake_connection()))
        self.rc = RefreshController(app=self.app)

    async def test_configure_snapd_kernel_autoinstall(self):
        # If a snap channel is supplied via kernel command line or
        # autoinstall data, switch to it.

        for src in SnapChannelSource.CMDLINE, SnapChannelSource.AUTOINSTALL:
            with mock.patch.object(self.rc, "get_refresh_channel") as grc:
                grc.return_value = ("newchan", src)
                with mock.patch.object(refresh_mod, "post_and_wait") as paw:
                    await self.rc.configure_snapd(context=self.rc.context)

            paw.assert_called_once()
            request = paw.mock_calls[0].args[2]
            self.assertEqual(request.action, snapdapi.SnapAction.SWITCH)
            self.assertEqual(request.channel, "newchan")

    async def test_configure_snapd_notfound(self):
        # If a snap channel is not found, ignore that.

        with mock.patch.object(self.rc, "get_refresh_channel") as grc:
            grc.return_value = (None, SnapChannelSource.NOT_FOUND)
            with mock.patch.object(refresh_mod, "post_and_wait") as paw:
                await self.rc.configure_snapd(context=self.rc.context)

        paw.assert_not_called()

    @mock.patch("subiquity.server.controllers.refresh.lsb_release")
    async def test_configure_snapd_disk_info(self, m_lsb):
        # If a snap channel is found via .disk/info it is applying if
        # and only if the snap is already tracking stable/ubuntu-XX.YY

        m_lsb.return_value = {"release": "XX.YY"}

        # The ...v2.snaps[snap_name].GET() style of API is cute but
        # not very easy to mock out.
        subiquity_info = await self.app.snapdapi.v2.snaps["subiquity"].GET()

        class StubSnap:
            async def GET(self):
                return subiquity_info

            POST = None

        stub_snaps = {"subiquity": StubSnap()}

        # Test with the snap following the expected channel
        subiquity_info.channel = "stable/ubuntu-XX.YY"

        with mock.patch.object(self.rc, "get_refresh_channel") as grc:
            grc.return_value = ("newchan", SnapChannelSource.DISK_INFO_FILE)
            with mock.patch.object(self.rc.app.snapdapi.v2, "snaps", new=stub_snaps):
                with mock.patch.object(refresh_mod, "post_and_wait") as paw:
                    await self.rc.configure_snapd(context=self.rc.context)

        paw.assert_called_once()
        request = paw.mock_calls[0].args[2]
        self.assertEqual(request.action, snapdapi.SnapAction.SWITCH)
        self.assertEqual(request.channel, "newchan")

        # Test with the snap not following the expected channel
        subiquity_info.channel = "something-custom"

        with mock.patch.object(self.rc, "get_refresh_channel") as grc:
            with mock.patch.object(self.rc.app.snapdapi.v2, "snaps", new=stub_snaps):
                grc.return_value = ("newchan", SnapChannelSource.DISK_INFO_FILE)
                with mock.patch.object(refresh_mod, "post_and_wait") as paw:
                    await self.rc.configure_snapd(context=self.rc.context)

        paw.assert_not_called()
