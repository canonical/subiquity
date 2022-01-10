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
import glob
import json
import logging
import os
import select
from typing import List

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
from subiquity.common.filesystem.actions import (
    DeviceAction,
    )
from subiquity.common.filesystem import boot, gaps, labels
from subiquity.common.filesystem.manipulator import FilesystemManipulator
from subiquity.common.types import (
    Bootloader,
    Disk,
    GuidedChoice,
    GuidedStorageResponse,
    ModifyPartitionV2,
    ProbeStatus,
    StorageResponse,
    StorageResponseV2,
    )
from subiquity.models.filesystem import (
    align_down,
    LVM_CHUNK_SIZE,
    Raid,
    )
from subiquity.server.controller import (
    SubiquityController,
    )


log = logging.getLogger("subiquity.server.controllers.filesystem")
block_discover_log = logging.getLogger('block-discover')


class FilesystemController(SubiquityController, FilesystemManipulator):

    endpoint = API.storage

    autoinstall_key = "storage"
    autoinstall_schema = {'type': 'object'}  # ...
    model_name = "filesystem"

    _configured = False

    def __init__(self, app):
        self.ai_data = {}
        super().__init__(app)
        self.model.target = app.base_model.target
        if self.opts.dry_run and self.opts.bootloader:
            name = self.opts.bootloader.upper()
            self.model.bootloader = getattr(Bootloader, name)
        self._monitor = None
        self._errors = {}
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

    async def configured(self):
        self._configured = True
        await super().configured()
        self.stop_listening_udev()

    @with_context()
    async def apply_autoinstall_config(self, context=None):
        await self._start_task
        await self._probe_task.wait()
        if False in self._errors:
            raise self._errors[False][0]
        if True in self._errors:
            raise self._errors[True][0]
        self.convert_autoinstall_config(context=context)
        if not self.model.is_root_mounted():
            raise Exception("autoinstall config did not mount root")
        if self.model.needs_bootloader_partition():
            raise Exception(
                "autoinstall config did not create needed bootloader "
                "partition")

    def guided_direct(self, disk):
        self.reformat(disk)
        result = {
            "size": gaps.largest_gap_size(disk),
            "fstype": "ext4",
            "mount": "/",
            }
        self.partition_disk_handler(disk, None, result)

    def guided_lvm(self, disk, lvm_options=None):
        self.reformat(disk)
        if DeviceAction.TOGGLE_BOOT in DeviceAction.supported(disk):
            self.add_boot_disk(disk)
        self.create_partition(
            device=disk, spec=dict(
                size=self._get_bootfs_size(disk),
                fstype="ext4",
                mount='/boot'
                ))
        part = self.create_partition(
            device=disk, spec=dict(
                size=gaps.largest_gap_size(disk),
                fstype=None,
                ))
        vg_name = 'ubuntu-vg'
        i = 0
        while self.model._one(type='lvm_volgroup', name=vg_name) is not None:
            i += 1
            vg_name = 'ubuntu-vg-{}'.format(i)
        spec = dict(name=vg_name, devices=set([part]))
        if lvm_options and lvm_options['encrypt']:
            spec['password'] = lvm_options['luks_options']['password']
        vg = self.create_volgroup(spec)
        # There's no point using LVM and unconditionally filling the
        # VG with a single LV, but we should use more of a smaller
        # disk to avoid the user running into out of space errors
        # earlier than they probably expect to.
        if vg.size < 10 * (1 << 30):
            # Use all of a small (<10G) disk.
            lv_size = vg.size
        elif vg.size < 20 * (1 << 30):
            # Use 10G of a smallish (<20G) disk.
            lv_size = 10 * (1 << 30)
        elif vg.size < 200 * (1 << 30):
            # Use half of a larger (<200G) disk.
            lv_size = vg.size // 2
        else:
            # Use at most 100G of a large disk.
            lv_size = 100 * (1 << 30)
        lv_size = align_down(lv_size, LVM_CHUNK_SIZE)
        self.create_logical_volume(
            vg=vg, spec=dict(
                size=lv_size,
                name="ubuntu-lv",
                fstype="ext4",
                mount="/",
                ))

    def guided(self, choice):
        disk = self.model._one(id=choice.disk_id)
        if choice.use_lvm:
            lvm_options = None
            if choice.password is not None:
                lvm_options = {
                    'encrypt': True,
                    'luks_options': {
                        'password': choice.password,
                        },
                    }
            self.guided_lvm(disk, lvm_options)
        else:
            self.guided_direct(disk)

    async def _probe_response(self, wait, resp_cls):
        if self._probe_task.task is None or not self._probe_task.task.done():
            if wait:
                await self._start_task
                await self._probe_task.wait()
            else:
                return resp_cls(status=ProbeStatus.PROBING)
        if True in self._errors:
            return resp_cls(
                status=ProbeStatus.FAILED,
                error_report=self._errors[True][1].ref())
        return None

    def full_probe_error(self):
        if False in self._errors:
            return self._errors[False][1].ref()
        else:
            return None

    async def GET(self, wait: bool = False) -> StorageResponse:
        probe_resp = await self._probe_response(wait, StorageResponse)
        if probe_resp is not None:
            return probe_resp
        return StorageResponse(
            status=ProbeStatus.DONE,
            bootloader=self.model.bootloader,
            error_report=self.full_probe_error(),
            orig_config=self.model._orig_config,
            config=self.model._render_actions(include_all=True),
            blockdev=self.model._probe_data['blockdev'],
            dasd=self.model._probe_data.get('dasd', {}))

    async def POST(self, config: list):
        log.debug(config)
        self.model._actions = self.model._actions_from_config(
            config, self.model._probe_data['blockdev'], is_probe_data=False)
        await self.configured()

    async def guided_GET(self, wait: bool = False) -> GuidedStorageResponse:
        probe_resp = await self._probe_response(wait, GuidedStorageResponse)
        if probe_resp is not None:
            return probe_resp
        # This calculation is pretty much a hack and we should
        # actually think about it at some point (like: maybe the
        # source catalog should directly specify the minimum suitable
        # size?)
        min_size = 2*self.app.base_model.source.current.size + (1 << 30)
        disks = []
        for raid in self.model._all(type='raid'):
            if not boot.can_be_boot_device(raid, with_reformatting=True):
                continue
            disks.append(raid)
        for disk in self.model._all(type='disk'):
            if not boot.can_be_boot_device(disk, with_reformatting=True):
                continue
            cd = disk.constructed_device()
            if isinstance(cd, Raid):
                can_be_boot = False
                for v in cd._subvolumes:
                    if boot.can_be_boot_device(v, with_reformatting=True):
                        can_be_boot = True
                if can_be_boot:
                    continue
            disks.append(disk)
        return GuidedStorageResponse(
            status=ProbeStatus.DONE,
            error_report=self.full_probe_error(),
            disks=[labels.for_client(d, min_size=min_size) for d in disks])

    async def guided_POST(self, data: GuidedChoice) -> StorageResponse:
        log.debug(data)
        self.guided(data)
        return await self.GET()

    async def reset_POST(self, context, request) -> StorageResponse:
        log.info("Resetting Filesystem model")
        self.model.reset()
        return await self.GET(context)

    async def has_rst_GET(self) -> bool:
        search = '/sys/module/ahci/drivers/pci:ahci/*/remapped_nvme'
        for remapped_nvme in glob.glob(search):
            with open(remapped_nvme, 'r') as f:
                if int(f.read()) > 0:
                    return True
        return False

    async def has_bitlocker_GET(self) -> List[Disk]:
        '''list of Disks that contain a partition that is BitLockered'''
        bitlockered_disks = []
        for disk in self.model.all_disks():
            for part in disk.partitions():
                fs = part.fs()
                if not fs:
                    continue
                fstype = fs.fstype
                if fstype == "BitLocker":
                    bitlockered_disks.append(disk)
                    break
        return [labels.for_client(disk) for disk in bitlockered_disks]

    def get_partition(self, disk, number):
        for p in disk.partitions():
            if p._number == number:
                return p
        raise ValueError(f'Partition {number} on {disk.id} not found')

    async def v2_GET(self) -> StorageResponseV2:
        disks = self.model._all(type='disk')
        return StorageResponseV2(
                disks=[labels.for_client(d) for d in disks],
                need_root=not self.model.is_root_mounted(),
                need_boot=self.model.needs_bootloader_partition(),
                )

    async def v2_POST(self) -> StorageResponseV2:
        await self.configured()
        return await self.v2_GET()

    async def v2_reset_POST(self) -> StorageResponseV2:
        log.info("Resetting Filesystem model")
        self.model.reset()
        return await self.v2_GET()

    async def v2_guided_POST(self, data: GuidedChoice) -> StorageResponseV2:
        log.debug(data)
        self.guided(data)
        return await self.v2_GET()

    async def v2_reformat_disk_POST(self, disk_id: str) -> StorageResponseV2:
        self.reformat(self.model._one(id=disk_id))
        return await self.v2_GET()

    async def v2_add_boot_partition_POST(self, disk_id: str) \
            -> StorageResponseV2:
        disk = self.model._one(id=disk_id)
        if boot.is_boot_device(disk):
            raise ValueError('device already has bootloader partition')
        if DeviceAction.TOGGLE_BOOT not in DeviceAction.supported(disk):
            raise ValueError("disk does not support boot partiton")
        self.add_boot_disk(disk)
        return await self.v2_GET()

    async def v2_add_partition_POST(self, data: ModifyPartitionV2) \
            -> StorageResponseV2:
        log.debug(data)
        if data.partition.format is None:
            raise ValueError('add_partition must supply format')
        if data.partition.boot is not None:
            raise ValueError('add_partition does not support changing boot')
        disk = self.model._one(id=data.disk_id)
        largest_size = gaps.largest_gap_size(disk)
        if largest_size == 0:
            raise ValueError('no space on disk')
        requested_size = data.partition.size or 0
        if requested_size > largest_size:
            raise ValueError('new partition too large')
        if requested_size < 1:
            requested_size = largest_size
        spec = {
            'size': requested_size,
            'fstype': data.partition.format,
            'mount': data.partition.mount,
        }

        self.create_partition(disk, spec, '', 'superblock', None)
        return await self.v2_GET()

    async def v2_delete_partition_POST(self, data: ModifyPartitionV2) \
            -> StorageResponseV2:
        log.debug(data)
        disk = self.model._one(id=data.disk_id)
        partition = self.get_partition(disk, data.partition.number)
        self.delete_partition(partition)
        return await self.v2_GET()

    async def v2_edit_partition_POST(self, data: ModifyPartitionV2) \
            -> StorageResponseV2:
        log.debug(data)
        disk = self.model._one(id=data.disk_id)
        partition = self.get_partition(disk, data.partition.number)
        if data.partition.size not in (None, partition.size):
            raise ValueError('edit_partition does not support changing size')
        if data.partition.boot is not None \
                and data.partition.boot != partition.boot:
            raise ValueError('edit_partition does not support changing boot')
        spec = {
            'fstype': data.partition.format or partition.format,
            'mount': data.partition.mount or partition.mount,
        }
        self.partition_disk_handler(disk, partition, spec)
        return await self.v2_GET()

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
        # It is possible for the user to submit filesystem config
        # while a probert probe is running. We don't want to overwrite
        # the users config with a blank one if this happens! (See
        # https://bugs.launchpad.net/bugs/1954848).
        if self._configured:
            return
        fpath = os.path.join(self.app.block_log_dir, fname)
        with open(fpath, 'w') as fp:
            json.dump(storage, fp, indent=4)
        self.app.note_file_for_apport(key, fpath)
        self.model.load_probe_data(storage)

    @with_context()
    async def _probe(self, *, context=None):
        self._errors = {}
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
            except Exception as exc:
                block_discover_log.exception(
                    "block probing failed restricted=%s", restricted)
                report = self.app.make_apport_report(kind, "block probing")
                if report is not None:
                    self._errors[restricted] = (exc, report)
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
            if not disk:
                raise Exception("autoinstall cannot configure storage "
                                "- no disk found large enough for install")
            meth(disk)
        elif 'config' in self.ai_data:
            self.model.apply_autoinstall_config(self.ai_data['config'])
            self.model.grub = self.ai_data.get('grub')
            self.model.swap = self.ai_data.get('swap')

    def start(self):
        if self.model.bootloader == Bootloader.PREP:
            self.supports_resilient_boot = False
        else:
            release = lsb_release(dry_run=self.app.opts.dry_run)['release']
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
