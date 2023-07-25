# Copyright 2018 Canonical, Ltd.
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
import logging
from typing import List

import attr
import requests.exceptions

from subiquity.common.apidef import API
from subiquity.common.types import (
    SnapCheckState,
    SnapInfo,
    SnapListResponse,
    SnapSelection,
)
from subiquity.server.controller import SubiquityController
from subiquity.server.types import InstallerChannels
from subiquitycore.async_helpers import schedule_task
from subiquitycore.context import with_context

log = logging.getLogger("subiquity.server.controllers.snaplist")


class SnapListFetchError(Exception):
    """Exception to raise when the list of snaps could not be fetched."""


class SnapdSnapInfoLoader:
    def __init__(self, model, snapd, store_section, context):
        self.model = model
        self.store_section = store_section
        self.context = context

        self.main_task = None

        self.snapd = snapd
        self.pending_snaps = []
        self.tasks = {}  # {snap:task}

        self.load_list_task_created = asyncio.Event()

    def _fetch_list_ended(self) -> bool:
        """Tells whether the snap list fetch task has ended without being
        cancelled."""
        if None not in self.tasks:
            return False
        task = self.get_snap_list_task()
        if task.cancelled():
            return False
        return task.done()

    def fetch_list_completed(self) -> bool:
        """Tells whether the snap list fetch task has completed."""
        if not self._fetch_list_ended():
            return False
        return not self.get_snap_list_task().exception()

    def fetch_list_failed(self) -> bool:
        """Tells whether the snap list fetch task has failed."""
        if not self._fetch_list_ended():
            return False
        return bool(self.get_snap_list_task().exception())

    def start(self):
        log.debug("loading list of snaps")
        self.main_task = schedule_task(self._start())

    async def _start(self):
        with self.context:
            task = self.tasks[None] = asyncio.create_task(self._load_list())
            self.load_list_task_created.set()
            try:
                await task
            except SnapListFetchError:
                log.exception("loading list of snaps failed")
                return
            self.pending_snaps = self.model.get_snap_list()
            log.debug("fetched list of %s snaps", len(self.pending_snaps))
            while self.pending_snaps:
                snap = self.pending_snaps.pop(0)
                task = self.tasks[snap] = schedule_task(
                    self._fetch_info_for_snap(snap=snap)
                )
                await task

    @with_context(name="list")
    async def _load_list(self, context=None):
        try:
            result = await self.snapd.get("v2/find", section=self.store_section)
        except requests.exceptions.RequestException:
            raise SnapListFetchError
        self.model.load_find_data(result)

    def stop(self):
        if self.main_task is not None:
            self.main_task.cancel()

    @with_context(name="fetch/{snap.name}")
    async def _fetch_info_for_snap(self, snap, context=None):
        try:
            data = await self.snapd.get("v2/find", name=snap.name)
        except requests.exceptions.RequestException:
            log.exception("loading snap info failed")
            # XXX something better here?
            return
        self.model.load_info_data(data)

    def get_snap_list_task(self):
        return self.tasks[None]

    def get_snap_info_task(self, snap):
        if snap not in self.tasks:
            if snap in self.pending_snaps:
                self.pending_snaps.remove(snap)
            self.tasks[snap] = schedule_task(self._fetch_info_for_snap(snap=snap))
        return self.tasks[snap]


class SnapListController(SubiquityController):
    endpoint = API.snaplist

    autoinstall_key = "snaps"
    autoinstall_default = []
    autoinstall_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "channel": {"type": "string"},
                "classic": {"type": "boolean"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    }
    model_name = "snaplist"

    interactive_for_variants = {"server"}

    def _make_loader(self):
        return SnapdSnapInfoLoader(
            self.model,
            self.app.snapd,
            self.opts.snap_section,
            self.context.child("loader"),
        )

    def __init__(self, app):
        super().__init__(app)
        self.loader = self._make_loader()
        self.app.hub.subscribe(
            InstallerChannels.SNAPD_NETWORK_CHANGE, self.snapd_network_changed
        )

    def load_autoinstall_data(self, ai_data):
        to_install = []
        for snap in ai_data:
            to_install.append(
                SnapSelection(
                    name=snap["name"],
                    channel=snap.get("channel", "stable"),
                    classic=snap.get("classic", False),
                )
            )
        self.model.set_installed_list(to_install)

    def snapd_network_changed(self):
        if not self.interactive():
            return
        # If the loader managed to load the list of snaps, the
        # network must basically be working.
        if self.loader.fetch_list_completed():
            return
        else:
            self.loader.stop()
        self.loader = self._make_loader()
        self.loader.start()

    def make_autoinstall(self):
        return [attr.asdict(sel) for sel in self.model.selections]

    async def GET(self, wait: bool = False) -> SnapListResponse:
        if (
            self.loader.fetch_list_failed()
            or not self.app.base_model.network.has_network
        ):
            return SnapListResponse(status=SnapCheckState.FAILED)
        if not self.loader.fetch_list_completed() and not wait:
            return SnapListResponse(status=SnapCheckState.LOADING)
        # Let's wait for the task to be completed.
        # If the loader gets restarted, the cancellation should be absorbed.
        while True:
            await self.loader.load_list_task_created.wait()
            try:
                await asyncio.shield(self.loader.get_snap_list_task())
            except SnapListFetchError:
                return SnapListResponse(status=SnapCheckState.FAILED)
            except asyncio.CancelledError:
                log.warning("load list snaps task was cancelled, retrying...")
            else:
                break
        return SnapListResponse(
            status=SnapCheckState.DONE,
            snaps=self.model.get_snap_list(),
            selections=self.model.selections,
        )

    async def POST(self, data: List[SnapSelection]):
        log.debug(data)
        self.model.set_installed_list(data)
        await self.configured()

    async def snap_info_GET(self, snap_name: str) -> SnapInfo:
        snap = self.model._snap_for_name(snap_name)
        await self.loader.get_snap_info_task(snap)
        return snap
