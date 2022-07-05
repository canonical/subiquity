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
import platform
import select
from typing import List

import pyudev

from subiquitycore.async_helpers import (
    run_in_thread,
    schedule_task,
    SingleInstanceTask,
    TaskAlreadyRunningError,
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
from subiquity.common.filesystem import boot, gaps, labels, sizes
from subiquity.common.filesystem.manipulator import (
    FilesystemManipulator,
)
from subiquity.common.types import (
    AddPartitionV2,
    Bootloader,
    Disk,
    GuidedChoice,
    GuidedChoiceV2,
    GuidedStorageResponse,
    GuidedStorageResponseV2,
    GuidedStorageTargetReformat,
    GuidedStorageTargetResize,
    GuidedStorageTargetUseGap,
    ModifyPartitionV2,
    ProbeStatus,
    ReformatDisk,
    StorageResponse,
    StorageResponseV2,
    )
from subiquity.models.filesystem import (
    align_up,
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
        self.model.storage_version = self.opts.storage_version
        self._monitor = None
        self._errors = {}
        self._probe_once_task = SingleInstanceTask(
            self._probe_once, propagate_errors=False)
        self._probe_task = SingleInstanceTask(
            self._probe, propagate_errors=False, cancel_restart=False)
        self.supports_resilient_boot = False

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

    def setup_disk_for_guided(self, target, mode):
        if isinstance(target, gaps.Gap):
            disk = target.device
            gap = target
        else:
            disk = target
            gap = None
        if mode is None or mode == 'reformat_disk':
            self.reformat(disk, wipe='superblock-recursive')
        if DeviceAction.TOGGLE_BOOT in DeviceAction.supported(disk):
            self.add_boot_disk(disk)
        if gap is None:
            return disk, gaps.largest_gap(disk)
        else:
            # find what's left of the gap after adding boot
            gap = gaps.within(disk, gap)
            if gap is None:
                raise Exception(f'failed to locate gap after adding boot')
            return disk, gap

    def guided_direct(self, target, mode=None):
        disk, gap = self.setup_disk_for_guided(target, mode)
        spec = dict(fstype="ext4", mount="/")
        self.create_partition(device=disk, gap=gap, spec=spec)

    def guided_lvm(self, target, mode=None, lvm_options=None):
        disk, gap = self.setup_disk_for_guided(target, mode)
        gap_boot, gap_rest = gap.split(sizes.get_bootfs_size(gap.size))
        spec = dict(fstype="ext4", mount='/boot')
        self.create_partition(device=disk, gap=gap_boot, spec=spec)

        part = self.create_partition(
                device=disk, gap=gap_rest, spec=dict(fstype=None))

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

    def guided(self, choice: GuidedChoiceV2):
        self.model.guided_configuration = choice

        disk = self.model._one(id=choice.target.disk_id)
        if isinstance(choice.target, GuidedStorageTargetReformat):
            mode = 'reformat_disk'
            target = disk
        elif isinstance(choice.target, GuidedStorageTargetUseGap):
            mode = 'use_gap'
            target = gaps.at_offset(disk, choice.target.gap.offset)
        elif isinstance(choice.target, GuidedStorageTargetResize):
            partition = self.get_partition(
                    disk, choice.target.partition_number)
            part_align = disk.alignment_data().part_align
            new_size = align_up(choice.target.new_size, part_align)
            if new_size > partition.size:
                raise Exception(f'Aligned requested size {new_size} too large')
            gap_offset = partition.offset + new_size
            partition.size = new_size
            partition.resize = True
            mode = 'use_gap'
            target = gaps.at_offset(disk, gap_offset)
        else:
            raise Exception(f'Unknown guided target {choice.target}')

        if choice.use_lvm:
            lvm_options = None
            if choice.password is not None:
                lvm_options = {
                    'encrypt': True,
                    'luks_options': {
                        'password': choice.password,
                        },
                    }
            self.guided_lvm(target, mode=mode, lvm_options=lvm_options)
        else:
            self.guided_direct(target, mode=mode)

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

    def _done_response(self):
        return StorageResponse(
            status=ProbeStatus.DONE,
            bootloader=self.model.bootloader,
            error_report=self.full_probe_error(),
            orig_config=self.model._orig_config,
            config=self.model._render_actions(include_all=True),
            blockdev=self.model._probe_data['blockdev'],
            dasd=self.model._probe_data.get('dasd', {}),
            storage_version=self.model.storage_version)

    async def GET(self, wait: bool = False) -> StorageResponse:
        probe_resp = await self._probe_response(wait, StorageResponse)
        if probe_resp is not None:
            return probe_resp
        return self._done_response()

    async def POST(self, config: list):
        log.debug(config)
        self.model._actions = self.model._actions_from_config(
            config, self.model._probe_data['blockdev'], is_probe_data=False)
        await self.configured()

    def get_guided_disks(self, check_boot=True, with_reformatting=False):
        disks = []
        for raid in self.model._all(type='raid'):
            if check_boot and not boot.can_be_boot_device(
                    raid, with_reformatting=with_reformatting):
                continue
            disks.append(raid)
        for disk in self.model._all(type='disk'):
            if check_boot and not boot.can_be_boot_device(
                    disk, with_reformatting=with_reformatting):
                continue
            cd = disk.constructed_device()
            if isinstance(cd, Raid):
                can_be_boot = False
                for v in cd._subvolumes:
                    if check_boot and boot.can_be_boot_device(
                            v, with_reformatting=with_reformatting):
                        can_be_boot = True
                if can_be_boot:
                    continue
            disks.append(disk)
        return disks

    async def guided_GET(self, wait: bool = False) -> GuidedStorageResponse:
        probe_resp = await self._probe_response(wait, GuidedStorageResponse)
        if probe_resp is not None:
            return probe_resp
        # This calculation is pretty much a hack and we should
        # actually think about it at some point (like: maybe the
        # source catalog should directly specify the minimum suitable
        # size?)
        min_size = 2*self.app.base_model.source.current.size + (1 << 30)
        disks = self.get_guided_disks(with_reformatting=True)
        return GuidedStorageResponse(
            status=ProbeStatus.DONE,
            error_report=self.full_probe_error(),
            disks=[labels.for_client(d, min_size=min_size) for d in disks])

    async def guided_POST(self, data: GuidedChoice) -> StorageResponse:
        log.debug(data)
        self.guided(GuidedChoiceV2.from_guided_choice(data))
        return self._done_response()

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
            if p.number == number:
                return p
        raise ValueError(f'Partition {number} on {disk.id} not found')

    def calculate_suggested_install_min(self):
        source_min = self.app.base_model.source.current.size
        align = max((pa.part_align
                     for pa in self.model._partition_alignment_data.values()))
        return sizes.calculate_suggested_install_min(source_min, align)

    async def v2_GET(self) -> StorageResponseV2:
        disks = self.model._all(type='disk')
        return StorageResponseV2(
                disks=[labels.for_client(d) for d in disks],
                need_root=not self.model.is_root_mounted(),
                need_boot=self.model.needs_bootloader_partition(),
                install_minimum_size=self.calculate_suggested_install_min(),
                )

    async def v2_POST(self) -> StorageResponseV2:
        await self.configured()
        return await self.v2_GET()

    async def v2_reset_POST(self) -> StorageResponseV2:
        log.info("Resetting Filesystem model")
        self.model.reset()
        return await self.v2_GET()

    async def v2_deprecated_guided_POST(self, data: GuidedChoice) \
            -> StorageResponseV2:
        log.debug(data)
        self.guided(GuidedChoiceV2.from_guided_choice(data))
        return await self.v2_GET()

    async def v2_guided_GET(self) -> GuidedStorageResponseV2:
        """Acquire a list of possible guided storage configuration scenarios.
        Results are sorted by the size of the space potentially available to
        the install."""

        scenarios = []
        install_min = self.calculate_suggested_install_min()

        for disk in self.get_guided_disks(with_reformatting=True):
            reformat = GuidedStorageTargetReformat(disk_id=disk.id)
            scenarios.append((disk.size, reformat))

        for disk in self.get_guided_disks(with_reformatting=False):
            gap = gaps.largest_gap(disk)
            if gap is not None and gap.size >= install_min:
                api_gap = labels.for_client(gap)
                use_gap = GuidedStorageTargetUseGap(
                        disk_id=disk.id,
                        gap=api_gap)
                scenarios.append((gap.size, use_gap))

        for disk in self.get_guided_disks(check_boot=False):
            part_align = disk.alignment_data().part_align
            for partition in disk.partitions():
                vals = sizes.calculate_guided_resize(
                        partition.estimated_min_size, partition.size,
                        install_min, part_align=part_align)
                if vals is None:
                    continue
                if not boot.can_be_boot_device(
                        disk, resize_partition=partition,
                        with_reformatting=False):
                    continue
                resize = GuidedStorageTargetResize.from_recommendations(
                        partition, vals)
                scenarios.append((vals.install_max, resize))

        scenarios.sort(reverse=True, key=lambda x: x[0])
        return GuidedStorageResponseV2(
                configured=self.model.guided_configuration,
                possible=[s[1] for s in scenarios])

    async def v2_guided_POST(self, data: GuidedChoiceV2) \
            -> GuidedStorageResponseV2:
        log.debug(data)
        self.guided(data)
        return await self.v2_guided_GET()

    async def v2_reformat_disk_POST(self, data: ReformatDisk) \
            -> StorageResponseV2:
        self.reformat(self.model._one(id=data.disk_id), data.ptable)
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

    async def v2_add_partition_POST(self, data: AddPartitionV2) \
            -> StorageResponseV2:
        log.debug(data)
        if data.partition.format is None:
            raise ValueError('add_partition must supply format')
        if data.partition.boot is not None:
            raise ValueError('add_partition does not support changing boot')
        disk = self.model._one(id=data.disk_id)
        requested_size = data.partition.size or 0
        if requested_size > data.gap.size:
            raise ValueError('new partition too large')
        if requested_size < 1:
            requested_size = data.gap.size
        spec = {
            'size': requested_size,
            'fstype': data.partition.format,
            'mount': data.partition.mount,
        }

        gap = gaps.at_offset(disk, data.gap.offset).split(requested_size)[0]
        self.create_partition(disk, gap, spec, wipe='superblock')
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
        if data.partition.size not in (None, partition.size) \
                and self.app.opts.storage_version < 2:
            raise ValueError('edit_partition does not support changing size')
        if data.partition.boot is not None \
                and data.partition.boot != partition.boot:
            raise ValueError('edit_partition does not support changing boot')
        spec = {'mount': data.partition.mount or partition.mount}
        if data.partition.format is not None \
                and data.partition.format != partition.format:
            spec['fstype'] = data.partition.format
        if data.partition.size is not None:
            spec['size'] = data.partition.size
        self.partition_disk_handler(disk, spec, partition=partition)
        return await self.v2_GET()

    @with_context(name='probe_once', description='restricted={restricted}')
    async def _probe_once(self, *, context, restricted):
        if restricted:
            probe_types = {'blockdev'}
            fname = 'probe-data-restricted.json'
            key = "ProbeDataRestricted"
        else:
            probe_types = {'defaults', 'filesystem_sizing'}
            if self.app.opts.use_os_prober:
                probe_types |= {'os'}
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
                if platform.machine() == 'riscv64':
                    # block probing is taking much longer on RISC-V - but why?
                    timeout = 60.0
                else:
                    timeout = 15.0
                await asyncio.wait_for(self._probe_once_task.task, timeout)
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

    def run_guided(self, layout):
        name = layout['name']
        guided_method = getattr(self, "guided_" + name)
        mode = layout.get('mode', 'reformat_disk')
        self.validate_layout_mode(mode)

        if mode == 'reformat_disk':
            match = layout.get("match", {'size': 'largest'})
            target = self.model.disk_for_match(self.model.all_disks(), match)
            if not target:
                raise Exception("autoinstall cannot configure storage "
                                "- no disk found large enough for install")
        elif mode == 'use_gap':
            bootable = [d for d in self.model.all_disks()
                        if boot.can_be_boot_device(d, with_reformatting=False)]
            gap = gaps.largest_gap(bootable)
            if not gap:
                raise Exception("autoinstall cannot configure storage "
                                "- no gap found large enough for install")
            # This is not necessarily the exact gap to be used, as the gap size
            # may change once add_boot_disk has sorted things out.
            target = gap
        log.info(f'autoinstall: running guided {name} install in mode {mode} '
                 f'using {target}')
        guided_method(target=target, mode=mode)

    def validate_layout_mode(self, mode):
        if mode not in ('reformat_disk', 'use_gap'):
            raise ValueError(f'Unknown layout mode {mode}')

    @with_context()
    def convert_autoinstall_config(self, context=None):
        log.debug("self.ai_data = %s", self.ai_data)
        if 'layout' in self.ai_data:
            self.run_guided(self.ai_data['layout'])
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
        try:
            self._probe_task.start_sync()
        except TaskAlreadyRunningError:
            log.debug('Skipping run of Probert - probe run already active')
        else:
            log.debug('Triggered Probert run on udev event')

    def make_autoinstall(self):
        rendered = self.model.render()
        r = {
            'config': rendered['storage']['config']
            }
        if 'swap' in rendered:
            r['swap'] = rendered['swap']
        return r
