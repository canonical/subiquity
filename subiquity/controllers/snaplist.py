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

import logging

import attr

import requests.exceptions

from subiquitycore.async_helpers import (
    schedule_task,
    )
from subiquitycore.context import with_context
from subiquitycore.controller import (
    Skip,
    )

from subiquity.common.types import (
    SnapCheckState,
    SnapListData,
    SnapSelection,
    )
from subiquity.controller import (
    SubiquityController,
    )
from subiquity.ui.views.snaplist import SnapListView

log = logging.getLogger('subiquity.controllers.snaplist')


class SnapdSnapInfoLoader:

    def __init__(self, model, snapd, store_section, context):
        self.model = model
        self.store_section = store_section
        self.context = context

        self.main_task = None
        self.snap_list_fetched = False
        self.failed = False

        self.snapd = snapd
        self.pending_info_snaps = []
        self.tasks = {}  # {snap:task}

    def start(self):
        log.debug("loading list of snaps")
        self.main_task = schedule_task(self._start())

    async def _start(self):
        with self.context:
            task = self.tasks[None] = schedule_task(self._load_list())
            await task
            self.pending_snaps = self.model.get_snap_list()
            log.debug("fetched list of %s snaps", len(self.pending_snaps))
            while self.pending_snaps:
                snap = self.pending_snaps.pop(0)
                task = self.tasks[snap] = schedule_task(
                    self._fetch_info_for_snap(snap=snap))
                await task

    @with_context(name="list")
    async def _load_list(self, context=None):
        try:
            result = await self.snapd.get(
                'v2/find', section=self.store_section)
        except requests.exceptions.RequestException:
            log.exception("loading list of snaps failed")
            self.failed = True
            return
        self.model.load_find_data(result)
        self.snap_list_fetched = True

    def stop(self):
        if self.main_task is not None:
            self.main_task.cancel()

    @with_context(name="fetch/{snap.name}")
    async def _fetch_info_for_snap(self, snap, context=None):
        try:
            data = await self.snapd.get('v2/find', name=snap.name)
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
            self.tasks[snap] = schedule_task(
                self._fetch_info_for_snap(snap=snap))
        return self.tasks[snap]


class SnapListController(SubiquityController):

    autoinstall_key = "snaps"
    autoinstall_default = []
    autoinstall_schema = {
        'type': 'array',
        'items': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'channel': {'type': 'string'},
                'classic': {'type': 'boolean'},
                },
            'required': ['name'],
            'additionalProperties': False,
            },
        }
    model_name = "snaplist"
    signals = [
        ('snapd-network-change', 'snapd_network_changed'),
    ]

    def _make_loader(self):
        return SnapdSnapInfoLoader(
            self.model, self.app.snapd, self.opts.snap_section,
            self.context.child("loader"))

    def __init__(self, app):
        super().__init__(app)
        self.loader = self._make_loader()

    def load_autoinstall_data(self, ai_data):
        to_install = []
        for snap in ai_data:
            to_install.append(SnapSelection(
                name=snap['name'],
                channel=snap.get('channel', 'stable'),
                is_classic=snap.get('classic', False)))
        self.model.set_installed_list(to_install)

    def snapd_network_changed(self):
        if not self.interactive():
            return
        # If the loader managed to load the list of snaps, the
        # network must basically be working.
        if self.loader.snap_list_fetched:
            return
        else:
            self.loader.stop()
        self.loader = self._make_loader()
        self.loader.start()

    def start_ui(self):
        if self.loader.failed or not self.app.base_model.network.has_network:
            # If loading snaps failed or the network is disabled, skip the
            # screen.
            self.configured()
            raise Skip()
        if 'snaps' in self.answers:
            selections = []
            for snap_name, selection in self.answers['snaps'].items():
                selections.append(SnapSelection(name=snap_name, **selection))
            self.done(selections)
            return
        self.ui.set_body(SnapListView(self))

    @property
    def snap_list_data(self):
        if self.loader.failed or not self.app.base_model.network.has_network:
            return SnapListData(status=SnapCheckState.FAILED)
        elif not self.loader.snap_list_fetched:
            return SnapListData(status=SnapCheckState.LOADING)
        else:
            return SnapListData(
                status=SnapCheckState.DONE,
                snaps=self.model.get_snap_list(),
                selections=self.model.selections)

    async def snap_list_data_wait(self):
        await self.loader.get_snap_list_task()
        return self.snap_list_data

    async def get_snap_info(self, snap):
        return await self.loader.get_snap_info_task(snap)

    def done(self, selections):
        log.debug(
            "SnapListController.done next_screen selections=%s",
            selections)
        self.model.set_installed_list(selections)
        self.configured()
        self.app.next_screen()

    def cancel(self, sender=None):
        self.app.prev_screen()

    def make_autoinstall(self):
        return [attr.asdict(selection) for selection in self.model.selections]
