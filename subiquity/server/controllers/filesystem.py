# Copyright 2015 Canonical, Ltd.
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
import json
import logging
import os
import select

import pyudev


from subiquitycore.async_helpers import (
    run_in_thread,
    schedule_task,
    SingleInstanceTask,
    )
from subiquitycore.context import with_context
from subiquitycore.utils import (
    run_command,
    )
from subiquitycore.lsb_release import lsb_release

from subiquity.common.apidef import API
from subiquity.common.errorreport import ErrorReportKind
from subiquity.common.filesystem import FilesystemManipulator
from subiquity.common.types import (
    ProbeStatus,
    StorageResponse,
    )
from subiquity.models.filesystem import (
    Bootloader,
    )
from subiquity.server.controller import (
    SubiquityController,
    )


log = logging.getLogger("subiquity.server.controller.filesystem")
block_discover_log = logging.getLogger('block-discover')


class FilesystemController(SubiquityController, FilesystemManipulator):

    endpoint = API.storage

    autoinstall_key = "storage"
    autoinstall_schema = {'type': 'object'}  # ...
    model_name = "filesystem"

    def __init__(self, app):
        self.ai_data = {}
        super().__init__(app)
        self.model.target = app.base_model.target
        if self.opts.dry_run and self.opts.bootloader:
            name = self.opts.bootloader.upper()
            self.model.bootloader = getattr(Bootloader, name)
        self._monitor = None
        self._crash_reports = {}
        self._probe_once_task = SingleInstanceTask(
            self._probe_once, propagate_errors=False)
        self._probe_task = SingleInstanceTask(
            self._probe, propagate_errors=False)

    def load_autoinstall_data(self, data):
        log.debug("load_autoinstall_data %s", data)
        if data is None:
            if not self.interactive():
                data = {
                    'layout': {
                        'name': 'lvm',
                        },
                    }
            else:
                data = {}
        log.debug("self.ai_data = %s", data)
        self.ai_data = data

    @with_context()
    async def apply_autoinstall_config(self, context=None):
        await self._start_task
        self.stop_listening_udev()
        await self._probe_task.wait()
        self.convert_autoinstall_config(context=context)
        if not self.model.is_root_mounted():
            raise Exception("autoinstall config did not mount root")
        if self.model.needs_bootloader_partition():
            raise Exception(
                "autoinstall config did not create needed bootloader "
                "partition")

    async def GET(self, wait: bool = False) -> StorageResponse:
        if self._probe_task.task is None or not self._probe_task.task.done():
            if wait:
                await self._start_task
                await self._probe_task.wait()
            else:
                return StorageResponse(status=ProbeStatus.PROBING)
        if True in self._crash_reports:
            return StorageResponse(
                status=ProbeStatus.FAILED,
                error_report=self._crash_reports[True].ref())
        else:
            if False in self._crash_reports:
                err_ref = self._crash_reports[False].ref()
            else:
                err_ref = None
            return StorageResponse(
                status=ProbeStatus.DONE,
                bootloader=self.model.bootloader,
                error_report=err_ref,
                orig_config=self.model._orig_config,
                config=self.model._render_actions(include_all=True),
                blockdev=self.model._probe_data['blockdev'])

    async def POST(self, config: list):
        self.model._actions = self.model._actions_from_config(
            config, self.model._probe_data['blockdev'], is_probe_data=False)
        self.configured()

    async def reset_POST(self, context, request) -> StorageResponse:
        log.info("Resetting Filesystem model")
        self.model.reset()
        return await self.GET(context)

    @with_context(name='probe_once', description='restricted={restricted}')
    async def _probe_once(self, *, context, restricted):
        if restricted:
            probe_types = {'blockdev'}
            fname = 'probe-data-restricted.json'
            key = "ProbeDataRestricted"
        else:
            probe_types = None
            fname = 'probe-data.json'
            key = "ProbeData"
        storage = await run_in_thread(
            self.app.prober.get_storage, probe_types)
        fpath = os.path.join(self.app.block_log_dir, fname)
        with open(fpath, 'w') as fp:
            json.dump(storage, fp, indent=4)
        self.app.note_file_for_apport(key, fpath)
        self.model.load_probe_data(storage)

    @with_context()
    async def _probe(self, *, context=None):
        self._crash_reports = {}
        for (restricted, kind) in [
                (False, ErrorReportKind.BLOCK_PROBE_FAIL),
                (True,  ErrorReportKind.DISK_PROBE_FAIL),
                ]:
            try:
                await self._probe_once_task.start(
                    context=context, restricted=restricted)
                # We wait on the task directly here, not
                # self._probe_once_task.wait as if _probe_once_task
                # gets cancelled, we should be cancelled too.
                await asyncio.wait_for(self._probe_once_task.task, 15.0)
            except asyncio.CancelledError:
                # asyncio.CancelledError is a subclass of Exception in
                # Python 3.6 (sadface)
                raise
            except Exception:
                block_discover_log.exception(
                    "block probing failed restricted=%s", restricted)
                report = self.app.make_apport_report(kind, "block probing")
                if report is not None:
                    self._crash_reports[restricted] = report
                continue
            break

    @with_context()
    def convert_autoinstall_config(self, context=None):
        log.debug("self.ai_data = %s", self.ai_data)
        if 'layout' in self.ai_data:
            layout = self.ai_data['layout']
            meth = getattr(self, "guided_" + layout['name'])
            disk = self.model.disk_for_match(
                self.model.all_disks(),
                layout.get("match", {'size': 'largest'}))
            meth(disk)
        elif 'config' in self.ai_data:
            self.model.apply_autoinstall_config(self.ai_data['config'])
            self.model.grub = self.ai_data.get('grub', {})
            self.model.swap = self.ai_data.get('swap')

    def start(self):
        if self.model.bootloader == Bootloader.PREP:
            self.supports_resilient_boot = False
        else:
            release = lsb_release()['release']
            self.supports_resilient_boot = release >= '20.04'
        self._start_task = schedule_task(self._start())

    async def _start(self):
        context = pyudev.Context()
        self._monitor = pyudev.Monitor.from_netlink(context)
        self._monitor.filter_by(subsystem='block')
        self._monitor.enable_receiving()
        self.start_listening_udev()
        await self._probe_task.start()

    def start_listening_udev(self):
        loop = asyncio.get_event_loop()
        loop.add_reader(self._monitor.fileno(), self._udev_event)

    def stop_listening_udev(self):
        loop = asyncio.get_event_loop()
        loop.remove_reader(self._monitor.fileno())

    def _udev_event(self):
        cp = run_command(['udevadm', 'settle', '-t', '0'])
        if cp.returncode != 0:
            log.debug("waiting 0.1 to let udev event queue settle")
            self.stop_listening_udev()
            loop = asyncio.get_event_loop()
            loop.call_later(0.1, self.start_listening_udev)
            return
        # Drain the udev events in the queue -- if we stopped listening to
        # allow udev to settle, it's good bet there is more than one event to
        # process and we don't want to kick off a full block probe for each
        # one.  It's a touch unfortunate that pyudev doesn't have a
        # non-blocking read so we resort to select().
        while select.select([self._monitor.fileno()], [], [], 0)[0]:
            action, dev = self._monitor.receive_device()
            log.debug("_udev_event %s %s", action, dev)
        self._probe_task.start_sync()

    def make_autoinstall(self):
        rendered = self.model.render()
        r = {
            'config': rendered['storage']['config']
            }
        if 'swap' in rendered:
            r['swap'] = rendered['swap']
        return r
