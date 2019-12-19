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

import asyncio
import enum
import logging
import os

import requests.exceptions

from subiquitycore.async_helpers import (
    schedule_task,
    SingleInstanceTask,
    )
from subiquitycore.controller import (
    BaseController,
    Skip,
    )


log = logging.getLogger('subiquity.controllers.refresh')


class CheckState(enum.IntEnum):
    UNKNOWN = enum.auto()
    AVAILABLE = enum.auto()
    UNAVAILABLE = enum.auto()


class RefreshController(BaseController):

    signals = [
        ('snapd-network-change', 'snapd_network_changed'),
    ]

    def __init__(self, app):
        super().__init__(app)
        self.snap_name = os.environ.get("SNAP_NAME", "subiquity")
        self.configure_task = None
        self.check_task = None

        self.current_snap_version = "unknown"
        self.new_snap_version = ""

        self.offered_first_time = False

    def start(self):
        self.configure_task = schedule_task(self.configure_snapd())
        self.check_task = SingleInstanceTask(
            self.check_for_update, propagate_errors=False)
        self.check_task.start_sync()

    @property
    def check_state(self):
        task = self.check_task.task
        if not task.done() or task.cancelled():
            return CheckState.UNKNOWN
        if task.exception():
            return CheckState.UNAVAILABLE
        return task.result()

    async def configure_snapd(self):
        with self.context.child("configure_snapd") as context:
            with context.child("get_details") as subcontext:
                try:
                    r = await self.app.snapd.get(
                        'v2/snaps/{snap_name}'.format(
                            snap_name=self.snap_name))
                except requests.exceptions.RequestException:
                    log.exception("getting snap details")
                    return
                self.current_snap_version = r['result']['version']
                for k in 'channel', 'revision', 'version':
                    self.app.note_data_for_apport(
                        "Snap" + k.title(), r['result'][k])
                subcontext.description = "current version of snap is: %r" % (
                    self.current_snap_version)
            channel = self.get_refresh_channel()
            desc = "switching {} to {}".format(self.snap_name, channel)
            with context.child("switching", desc) as subcontext:
                try:
                    await self.app.snapd.post_and_wait(
                        'v2/snaps/{}'.format(self.snap_name),
                        {'action': 'switch', 'channel': channel})
                except requests.exceptions.RequestException:
                    log.exception("switching channels")
                    return
                subcontext.description = "switched to " + channel

    def get_refresh_channel(self):
        """Return the channel we should refresh subiquity to."""
        if 'channel' in self.answers:
            return self.answers['channel']
        with open('/proc/cmdline') as fp:
            cmdline = fp.read()
        prefix = "subiquity-channel="
        for arg in cmdline.split():
            if arg.startswith(prefix):
                log.debug(
                    "get_refresh_channel: found %s on kernel cmdline", arg)
                return arg[len(prefix):]

        info_file = '/cdrom/.disk/info'
        try:
            fp = open(info_file)
        except FileNotFoundError:
            if self.opts.dry_run:
                info = (
                    'Ubuntu-Server 18.04.2 LTS "Bionic Beaver" - '
                    'Release amd64 (20190214.3)')
            else:
                log.debug(
                    "get_refresh_channel: failed to find .disk/info file")
                return
        else:
            with fp:
                info = fp.read()
        release = info.split()[1]
        return 'stable/ubuntu-' + release

    def snapd_network_changed(self):
        if self.check_state == CheckState.UNKNOWN:
            self.check_task.start_sync()

    async def check_for_update(self):
        await asyncio.shield(self.configure_task)
        with self.context.child("check_for_update") as context:
            if self.app.updated:
                context.description = (
                    "not offered update when already updated")
                return CheckState.UNAVAILABLE
            result = await self.app.snapd.get('v2/find', select='refresh')
            log.debug("check_for_update received %s", result)
            for snap in result["result"]:
                if snap["name"] == self.snap_name:
                    self.new_snap_version = snap["version"]
                    context.description = (
                        "new version of snap available: %r"
                        % self.new_snap_version)
                    return CheckState.AVAILABLE
            else:
                context.description = (
                    "no new version of snap available")
            return CheckState.UNAVAILABLE

    async def start_update(self):
        update_marker = os.path.join(self.app.state_dir, 'updating')
        open(update_marker, 'w').close()
        with self.context.child("starting_update") as context:
            change = await self.app.snapd.post(
                'v2/snaps/{}'.format(self.snap_name),
                {'action': 'refresh'})
            context.description = "change id: {}".format(change)
            return change

    async def get_progress(self, change):
        result = await self.app.snapd.get('v2/changes/{}'.format(change))
        return result['result']

    def start_ui(self, index=1):
        from subiquity.ui.views.refresh import RefreshView
        if self.app.updated:
            raise Skip()
        show = False
        if index == 1:
            if self.check_state == CheckState.AVAILABLE:
                show = True
                self.offered_first_time = True
        elif index == 2:
            if not self.offered_first_time:
                if self.check_state in [CheckState.UNKNOWN,
                                        CheckState.AVAILABLE]:
                    show = True
        else:
            raise AssertionError("unexpected index {}".format(index))
        if show:
            self.ui.set_body(RefreshView(self))
        else:
            raise Skip()

    def done(self, sender=None):
        log.debug("RefreshController.done next_screen")
        self.app.next_screen()

    def cancel(self, sender=None):
        self.app.prev_screen()
