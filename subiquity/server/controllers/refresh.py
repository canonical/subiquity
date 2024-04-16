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
from typing import Tuple

import requests.exceptions

from subiquity.common.apidef import API
from subiquity.common.types import Change, RefreshCheckState, RefreshStatus
from subiquity.server.controller import SubiquityController
from subiquity.server.snapdapi import (
    SnapAction,
    SnapActionRequest,
    TaskStatus,
    post_and_wait,
)
from subiquity.server.types import InstallerChannels
from subiquitycore.async_helpers import SingleInstanceTask, schedule_task
from subiquitycore.context import with_context
from subiquitycore.lsb_release import lsb_release

log = logging.getLogger("subiquity.server.controllers.refresh")


class SnapChannelSource(enum.Enum):
    CMDLINE = enum.auto()
    AUTOINSTALL = enum.auto()
    DISK_INFO_FILE = enum.auto()
    NOT_FOUND = enum.auto()


class RefreshController(SubiquityController):
    endpoint = API.refresh

    autoinstall_key = "refresh-installer"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "update": {"type": "boolean"},
            "channel": {"type": "string"},
        },
        "additionalProperties": False,
    }

    def __init__(self, app):
        super().__init__(app)
        self.ai_data = {}
        self.snap_name = os.environ.get("SNAP_NAME", "subiquity")
        self.configure_task = None
        self.check_task = None
        self.status = RefreshStatus(availability=RefreshCheckState.UNKNOWN)
        self.app.hub.subscribe(
            InstallerChannels.SNAPD_NETWORK_CHANGE, self.snapd_network_changed
        )

    def load_autoinstall_data(self, data):
        if data is not None:
            self.ai_data = data

    @property
    def active(self):
        if "update" in self.ai_data:
            return self.ai_data["update"]
        else:
            return self.interactive()

    def start(self):
        if not self.active:
            return
        self.configure_task = schedule_task(self.configure_snapd())
        self.check_task = SingleInstanceTask(
            self.check_for_update, propagate_errors=False
        )
        self.check_task.start_sync()

    @with_context()
    async def apply_autoinstall_config(self, context, index=1):
        if not self.active:
            return
        try:
            await asyncio.wait_for(self.check_task.wait(), 60)
        except asyncio.TimeoutError:
            return
        if self.status.availability != RefreshCheckState.AVAILABLE:
            return
        change_id = await self.start_update(context=context)
        while True:
            change = await self.get_progress(change_id)
            if change.status not in [TaskStatus.DO, TaskStatus.DOING, TaskStatus.DONE]:
                raise Exception(f"update failed: {change.status}")
            await asyncio.sleep(0.1)

    @with_context()
    async def configure_snapd(self, context):
        # Fetch information about snap from snapd. If the snap channel
        # to follow has been set on the kernel command line or
        # autoinstall data, switch to that. If the snap channel being
        # followed looks like the usual stable/ubuntu-XX.YY, look in
        # the .disk/info file to see if this is point release media
        # and switch to stable/ubuntu-XX.YY.Z if it is.
        with context.child("get_details") as subcontext:
            try:
                snap = await self.app.snapdapi.v2.snaps[self.snap_name].GET()
            except requests.exceptions.RequestException:
                log.exception("getting snap details")
                return
            self.status.current_snap_version = snap.version
            for k in "channel", "revision", "version":
                self.app.note_data_for_apport("Snap" + k.title(), getattr(snap, k))
            subcontext.description = "current version of snap is: %r" % (
                self.status.current_snap_version
            )
        (channel, source) = self.get_refresh_channel()
        if source == SnapChannelSource.NOT_FOUND:
            log.debug("no refresh channel found")
            return
        info = lsb_release(dry_run=self.app.opts.dry_run)
        expected_channel = "stable/ubuntu-" + info["release"]
        if (
            source == SnapChannelSource.DISK_INFO_FILE
            and snap.channel != expected_channel
        ):
            log.debug(
                f"snap tracking {snap.channel}, not resetting based on .disk/info"
            )
            return
        desc = "switching {} to {}".format(self.snap_name, channel)
        with context.child("switching", desc) as subcontext:
            try:
                await post_and_wait(
                    self.app.snapdapi,
                    self.app.snapdapi.v2.snaps[self.snap_name].POST,
                    SnapActionRequest(action=SnapAction.SWITCH, channel=channel),
                )
            except requests.exceptions.RequestException:
                log.exception("switching channels")
                return
            subcontext.description = "switched to " + channel

    def get_refresh_channel(self) -> Tuple[str, SnapChannelSource]:
        """Return the channel we should refresh subiquity to."""
        channel = self.app.kernel_cmdline.get("subiquity-channel")
        if channel is not None:
            log.debug("get_refresh_channel: found %s on kernel cmdline", channel)
            return (channel, SnapChannelSource.CMDLINE)
        if "channel" in self.ai_data:
            return (self.ai_data["channel"], SnapChannelSource.AUTOINSTALL)

        info_file = "/cdrom/.disk/info"
        try:
            fp = open(info_file)
        except FileNotFoundError:
            if self.opts.dry_run:
                info = (
                    'Ubuntu-Server 18.04.2 LTS "Bionic Beaver" - '
                    "Release amd64 (20190214.3)"
                )
            else:
                log.debug("get_refresh_channel: failed to find .disk/info file")
                return (None, SnapChannelSource.NOT_FOUND)
        else:
            with fp:
                info = fp.read()
        release = info.split()[1]
        return ("stable/ubuntu-" + release, SnapChannelSource.DISK_INFO_FILE)

    def snapd_network_changed(self):
        if self.active and self.status.availability == RefreshCheckState.UNKNOWN:
            self.check_task.start_sync()

    @with_context()
    async def check_for_update(self, context):
        await asyncio.shield(self.configure_task)
        if self.app.updated:
            context.description = "not offered update when already updated"
            self.status.availability = RefreshCheckState.UNAVAILABLE
            return
        try:
            result = await self.app.snapdapi.v2.find.GET(select="refresh")
        except requests.exceptions.RequestException:
            log.exception("checking for snap update failed")
            context.description = "checking for snap update failed"
            self.status.availability = RefreshCheckState.UNKNOWN
            return
        log.debug("check_for_update received %s", result)
        for snap in result:
            if snap.name != self.snap_name:
                continue
            self.status.new_snap_version = snap.version
            context.description = (
                "new version of snap available: %r" % self.status.new_snap_version
            )
            self.status.availability = RefreshCheckState.AVAILABLE
            return
        else:
            context.description = "no new version of snap available"
        self.status.availability = RefreshCheckState.UNAVAILABLE

    @with_context()
    async def start_update(self, context):
        try:
            change_id = await self.app.snapdapi.v2.snaps[self.snap_name].POST(
                SnapActionRequest(action=SnapAction.REFRESH, ignore_running=True)
            )
        except requests.exceptions.HTTPError as http_err:
            log.warning(
                "v2/snaps/%s returned %s", self.snap_name, http_err.response.text
            )
            raise
        context.description = "change id: {}".format(change_id)
        return change_id

    async def get_progress(self, change_id: str) -> Change:
        change = await self.app.snapdapi.v2.changes[change_id].GET()
        if change.status == TaskStatus.DONE:
            # Clearly if we got here we didn't get restarted by
            # snapd/systemctl (dry-run mode)
            self.app.restart()
        return change

    async def GET(self, wait: bool = False) -> RefreshStatus:
        if self.active and wait:
            await self.check_task.wait()
        return self.status

    async def POST(self, context) -> str:
        return await self.start_update(context=context)

    async def progress_GET(self, change_id: str) -> Change:
        return await self.get_progress(change_id)
