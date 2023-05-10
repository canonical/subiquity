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
import functools
import glob
import json
import logging
import os
import pathlib
import select
import time
from typing import Any, Dict, List, Optional, Set

import attr

from curtin.commands.extract import AbstractSourceHandler
from curtin.storage_config import ptable_uuid_to_flag_entry

import pyudev

from subiquitycore.async_helpers import (
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
from subiquity.common.filesystem import (
    boot,
    gaps,
    labels,
    sizes,
)
from subiquity.common.filesystem.manipulator import (
    FilesystemManipulator,
)
from subiquity.common.types import (
    AddPartitionV2,
    Bootloader,
    Disk,
    GuidedCapability,
    GuidedChoice,
    GuidedChoiceV2,
    GuidedStorageResponse,
    GuidedStorageResponseV2,
    GuidedStorageTarget,
    GuidedStorageTargetReformat,
    GuidedStorageTargetResize,
    GuidedStorageTargetUseGap,
    ModifyPartitionV2,
    ProbeStatus,
    ReformatDisk,
    SizingPolicy,
    StorageResponse,
    StorageResponseV2,
    )
from subiquity.models.filesystem import (
    ActionRenderMode,
    ArbitraryDevice,
    align_up,
    align_down,
    _Device,
    Disk as ModelDisk,
    LVM_CHUNK_SIZE,
    Raid,
    )
from subiquity.server.controller import (
    SubiquityController,
    )
from subiquity.server import snapdapi
from subiquity.server.mounter import Mounter
from subiquity.server.snapdapi import (
    StorageEncryptionSupport,
    StorageSafety,
    SystemDetails,
    )
from subiquity.server.types import InstallerChannels


log = logging.getLogger("subiquity.server.controllers.filesystem")
block_discover_log = logging.getLogger('block-discover')


# for translators: 'reason' is the reason FDE is unavailable.
system_defective_encryption_text = _(
    "TPM backed full-disk encryption is not available "
    "on this device (the reason given was \"{reason}\")."
)

system_multiple_volumes_text = _(
    "TPM backed full-disk encryption is not yet supported when "
    "the target spans multiple volumes."
)

system_non_gpt_text = _(
    "TPM backed full-disk encryption is only supported with a target volume "
    "partition table of GPT."
)


class NoSnapdSystemsOnSource(Exception):
    pass


@attr.s(auto_attribs=True)
class VariationInfo:
    name: str
    label: Optional[str]
    capabilities: Set[GuidedCapability]
    error: str = ''
    encryption_unavailable_reason: str = ''
    min_size: Optional[int] = None
    system: Optional[SystemDetails] = None

    def is_core_boot_classic(self) -> bool:
        return self.label is not None

    def is_valid(self) -> bool:
        return self.error == ''

    @classmethod
    def classic(cls, name: str, min_size: int):
        return cls(
            name=name,
            label=None,
            min_size=min_size,
            capabilities={
                GuidedCapability.DIRECT,
                GuidedCapability.LVM,
                GuidedCapability.LVM_LUKS
            })


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
        self._examine_systems_task = SingleInstanceTask(self._examine_systems)
        self.supports_resilient_boot = False
        self.app.hub.subscribe(
            (InstallerChannels.CONFIGURED, 'source'),
            self._examine_systems_task.start_sync)
        self._variation_info: Dict[str, VariationInfo] = {}
        self._info: Optional[VariationInfo] = None
        self._on_volume: Optional[snapdapi.OnVolume] = None
        self._source_handler: Optional[AbstractSourceHandler] = None
        self._system_mounter: Optional[Mounter] = None
        self._role_to_device: Dict[str: _Device] = {}
        self._device_to_structure: Dict[_Device: snapdapi.OnVolume] = {}
        self.use_tpm: bool = False
        self.locked_probe_data: bool = False
        # If probe data come in while we are doing partitioning, store it in
        # this variable. It will be picked up on next reset.
        self.queued_probe_data: Optional[Dict[str, Any]] = None

    def is_core_boot_classic(self):
        return self._info.is_core_boot_classic()

    def load_autoinstall_data(self, data):
        # Log disabled to prevent LUKS password leak
        # log.debug("load_autoinstall_data %s", data)
        # log.debug("self.ai_data = %s", data)
        self.ai_data = data

    async def configured(self):
        self._configured = True
        if self._info is None:
            self.set_info_for_capability(GuidedCapability.DIRECT)
        await super().configured()
        self.stop_listening_udev()

    async def _mount_systems_dir(self, variation_name):
        self._source_handler = \
                self.app.controllers.Source.get_handler(variation_name)
        source_path = self._source_handler.setup()
        cur_systems_dir = '/var/lib/snapd/seed/systems'
        source_systems_dir = os.path.join(source_path, cur_systems_dir[1:])
        if self.app.opts.dry_run:
            systems_dir_exists = self.app.dr_cfg.systems_dir_exists
        else:
            systems_dir_exists = pathlib.Path(source_systems_dir).is_dir()
        if not systems_dir_exists:
            raise NoSnapdSystemsOnSource
        self._system_mounter = Mounter(self.app)
        await self._system_mounter.bind_mount_tree(
            source_systems_dir, cur_systems_dir)

        cur_snaps_dir = '/var/lib/snapd/seed/snaps'
        source_snaps_dir = os.path.join(source_path, cur_snaps_dir[1:])
        if not self.app.opts.dry_run:
            await self._system_mounter.bind_mount_tree(
                source_snaps_dir, cur_snaps_dir)

    async def _unmount_systems_dir(self):
        if self._system_mounter is not None:
            await self._system_mounter.cleanup()
            self._system_mounter = None
        if self._source_handler is not None:
            self._source_handler.cleanup()
            self._source_handler = None

    async def _get_system(self, variation_name, label):
        try:
            await self._mount_systems_dir(variation_name)
        except NoSnapdSystemsOnSource:
            return None
        try:
            system = await self.app.snapdapi.v2.systems[label].GET()
        finally:
            await self._unmount_systems_dir()
        log.debug("got system %s", system)
        return system

    def info_for_system(self, name: str, label: str, system: SystemDetails):
        info = VariationInfo(
            name=name,
            label=label,
            capabilities=[],
            system=system,
            )

        if len(system.volumes) > 1:
            info.error = system_multiple_volumes_text
            return info

        [volume] = system.volumes.values()
        if volume.schema != 'gpt':
            info.error = system_non_gpt_text
            return info

        se = system.storage_encryption
        if se.support == StorageEncryptionSupport.DEFECTIVE:
            info.error = system_defective_encryption_text.format(
                  reason=se.unavailable_reason)
            return info

        offsets_and_sizes = list(
            self._offsets_and_sizes_for_volume(volume))
        _structure, last_offset, last_size = offsets_and_sizes[-1]
        info.min_size = last_offset + last_size

        if se.support == StorageEncryptionSupport.DISABLED:
            info.encryption_unavailable_reason = _(
                "TPM backed full-disk encryption has been disabled")
            info.capabilities = {
                GuidedCapability.CORE_BOOT_UNENCRYPTED}
        elif se.support == StorageEncryptionSupport.UNAVAILABLE:
            log.debug(
                "storage encryption unavailable: %r", se.unavailable_reason)
            info.encryption_unavailable_reason = se.unavailable_reason
            info.capabilities = {
                GuidedCapability.CORE_BOOT_UNENCRYPTED}
        else:
            if se.storage_safety == StorageSafety.ENCRYPTED:
                info.capabilities = {
                    GuidedCapability.CORE_BOOT_ENCRYPTED}
            elif se.storage_safety == StorageSafety.PREFER_ENCRYPTED:
                info.capabilities = {
                    GuidedCapability.CORE_BOOT_PREFER_ENCRYPTED}
            elif se.storage_safety == StorageSafety.PREFER_UNENCRYPTED:
                info.capabilities = {
                    GuidedCapability.CORE_BOOT_PREFER_UNENCRYPTED}

        return info

    async def _examine_systems(self):
        catalog_entry = self.app.base_model.source.current
        for name, variation in catalog_entry.variations.items():
            system = None
            label = variation.snapd_system_label
            if label is not None:
                system = await self._get_system(name, label)
            log.debug("got system %s for variation %s", system, name)
            if system is not None and len(system.volumes) > 0:
                self._variation_info[name] = self.info_for_system(
                    name, label, system)
            else:
                # This calculation is pretty much a hack and we should
                # actually think about it at some point (like: maybe the
                # source catalog should directly specify the minimum suitable
                # size?)
                min_size = 2*variation.size + (1 << 30)
                self._variation_info[name] = VariationInfo.classic(
                    name=name, min_size=min_size)

    @with_context()
    async def apply_autoinstall_config(self, context=None):
        await self._start_task
        await self._probe_task.wait()
        await self._examine_systems_task.wait()
        if False in self._errors:
            raise self._errors[False][0]
        if True in self._errors:
            raise self._errors[True][0]
        if self.ai_data is None:
            # If there are any classic variations, we default that.
            if any(not variation.is_core_boot_classic()
                   for variation in self._variation_info.values()
                   if variation.is_valid()):
                self.ai_data = {
                    'layout': {
                        'name': 'lvm',
                        },
                    }
            else:
                self.ai_data = {
                    'layout': {
                        'name': 'hybrid',
                        },
                    }
        await self.convert_autoinstall_config(context=context)
        if not self.model.is_root_mounted():
            raise Exception("autoinstall config did not mount root")
        if self.model.needs_bootloader_partition():
            raise Exception(
                "autoinstall config did not create needed bootloader "
                "partition")

    def update_devices(self, device_map):
        for action in self.model._actions:
            path = device_map.get(action.id)
            if path is not None:
                log.debug("recording path %r for device %s", path, action.id)
                action.path = path
                if action in self._device_to_structure:
                    self._device_to_structure[action].device = path

    def guided_direct(self, gap):
        spec = dict(fstype="ext4", mount="/")
        self.create_partition(device=gap.device, gap=gap, spec=spec)

    def guided_lvm(self, gap, choice: GuidedChoiceV2):
        device = gap.device
        part_align = device.alignment_data().part_align
        bootfs_size = align_up(sizes.get_bootfs_size(gap.size), part_align)
        gap_boot, gap_rest = gap.split(bootfs_size)
        spec = dict(fstype="ext4", mount='/boot')
        self.create_partition(device, gap_boot, spec)
        part = self.create_partition(device, gap_rest, dict(fstype=None))

        vg_name = 'ubuntu-vg'
        i = 0
        while self.model._one(type='lvm_volgroup', name=vg_name) is not None:
            i += 1
            vg_name = 'ubuntu-vg-{}'.format(i)
        spec = dict(name=vg_name, devices=set([part]))
        if choice.password is not None:
            spec['passphrase'] = choice.password
        vg = self.create_volgroup(spec)
        if choice.sizing_policy == SizingPolicy.SCALED:
            lv_size = sizes.scaled_rootfs_size(vg.size)
            lv_size = align_down(lv_size, LVM_CHUNK_SIZE)
        elif choice.sizing_policy == SizingPolicy.ALL:
            lv_size = vg.size
        else:
            raise Exception(f'Unhandled size policy {choice.sizing_policy}')
        log.debug(f'lv_size {lv_size} for {choice.sizing_policy}')
        self.create_logical_volume(
            vg=vg, spec=dict(
                size=lv_size,
                name="ubuntu-lv",
                fstype="ext4",
                mount="/",
                ))

    @functools.singledispatchmethod
    def start_guided(self, target: GuidedStorageTarget,
                     disk: ModelDisk) -> gaps.Gap:
        """Setup changes to the disk to prepare the gap that we will be
        doing a guided install into."""
        raise NotImplementedError(target)

    @start_guided.register
    def start_guided_reformat(self, target: GuidedStorageTargetReformat,
                              disk: ModelDisk) -> gaps.Gap:
        """Perform the reformat, and return the resulting gap."""
        self.reformat(disk, wipe='superblock-recursive')
        return gaps.largest_gap(disk)

    @start_guided.register
    def start_guided_use_gap(self, target: GuidedStorageTargetUseGap,
                             disk: ModelDisk) -> gaps.Gap:
        """Lookup the matching model gap."""
        return gaps.at_offset(disk, target.gap.offset)

    @start_guided.register
    def start_guided_resize(self, target: GuidedStorageTargetResize,
                            disk: ModelDisk) -> gaps.Gap:
        """Perform the resize of the target partition,
        and return the resulting gap."""
        partition = self.get_partition(disk, target.partition_number)
        part_align = disk.alignment_data().part_align
        new_size = align_up(target.new_size, part_align)
        if new_size > partition.size:
            raise Exception(f'Aligned requested size {new_size} too large')
        partition.size = new_size
        partition.resize = True
        # Calculating where that gap will be can be tricky due to alignment
        # needs and the possibility that we may be splitting a logical
        # partition, which needs an extra 1MiB spacer.
        gap = gaps.after(disk, partition.offset)
        if gap is None:
            pgs = gaps.parts_and_gaps(disk)
            raise Exception(f'gap not found after resize, pgs={pgs}')
        return gap

    def set_info_for_capability(self, capability: GuidedCapability):
        d = {
            GuidedCapability.CORE_BOOT_ENCRYPTED: {
                GuidedCapability.CORE_BOOT_ENCRYPTED,
                GuidedCapability.CORE_BOOT_PREFER_ENCRYPTED,
                GuidedCapability.CORE_BOOT_PREFER_UNENCRYPTED,
                },
            GuidedCapability.CORE_BOOT_UNENCRYPTED: {
                GuidedCapability.CORE_BOOT_UNENCRYPTED,
                GuidedCapability.CORE_BOOT_PREFER_ENCRYPTED,
                GuidedCapability.CORE_BOOT_PREFER_UNENCRYPTED,
                },
            }
        for info in self._variation_info.values():
            if not info.is_valid():
                continue
            if d.get(capability, {capability}) & info.capabilities:
                self._info = info
                return
        raise Exception(
            "could not find variation for {}".format(capability))

    async def guided(self, choice: GuidedChoiceV2):
        self.model.guided_configuration = choice

        self.set_info_for_capability(choice.capability)

        disk = self.model._one(id=choice.target.disk_id)

        if self.is_core_boot_classic():
            assert isinstance(choice.target, GuidedStorageTargetReformat)
            self.use_tpm = (
                choice.capability == GuidedCapability.CORE_BOOT_ENCRYPTED)
            await self.guided_core_boot(disk)
            return

        gap = self.start_guided(choice.target, disk)
        if DeviceAction.TOGGLE_BOOT in DeviceAction.supported(disk):
            self.add_boot_disk(disk)
        # find what's left of the gap after adding boot
        gap = gap.within()
        if gap is None:
            raise Exception('failed to locate gap after adding boot')

        if choice.capability.is_lvm():
            self.guided_lvm(gap, choice)
        elif choice.capability == GuidedCapability.DIRECT:
            self.guided_direct(gap)
        else:
            raise ValueError('cannot process capability')

    async def _probe_response(self, wait, resp_cls):
        if not self._probe_task.done():
            if wait:
                await self._start_task
                await self._probe_task.wait()
            else:
                return resp_cls(status=ProbeStatus.PROBING)
        if True in self._errors:
            return resp_cls(
                status=ProbeStatus.FAILED,
                error_report=self._errors[True][1].ref())
        if not self._examine_systems_task.done():
            if wait:
                await self._examine_systems_task.wait()
            else:
                return resp_cls(status=ProbeStatus.PROBING)
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
            config=self.model._render_actions(mode=ActionRenderMode.ALL),
            blockdev=self.model._probe_data['blockdev'],
            dasd=self.model._probe_data.get('dasd', {}),
            storage_version=self.model.storage_version)

    async def GET(self, wait: bool = False, use_cached_result: bool = False) \
            -> StorageResponse:
        if not use_cached_result:
            probe_resp = await self._probe_response(wait, StorageResponse)
            if probe_resp is not None:
                return probe_resp
        return self._done_response()

    async def POST(self, config: list):
        log.debug(config)
        self.model._actions, self.model._exclusions = \
            self.model._actions_from_config(
                config, self.model._probe_data['blockdev'],
                is_probe_data=False)
        await self.configured()

    def potential_boot_disks(self, check_boot=True, with_reformatting=False):
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
        return [d for d in disks if d not in self.model._exclusions]

    async def guided_GET(self, wait: bool = False) -> GuidedStorageResponse:
        probe_resp = await self._probe_response(wait, GuidedStorageResponse)
        if probe_resp is not None:
            return probe_resp
        disks = self.potential_boot_disks(with_reformatting=True)

        # Choose the first non-core-boot one offered.  If we only have
        # core-boot choices, choose the first of those.
        core_boot_info = None
        for info in self._variation_info.values():
            if not info.is_valid():
                continue
            if not info.is_core_boot_classic():
                break
            if core_boot_info is None:
                core_boot_info = info
        else:
            info = core_boot_info

        return GuidedStorageResponse(
            status=ProbeStatus.DONE,
            error_report=self.full_probe_error(),
            disks=[
                labels.for_client(d, min_size=info.min_size) for d in disks
                ],
            core_boot_classic_error=info.error,
            encryption_unavailable_reason=info.encryption_unavailable_reason,
            capabilities=list(info.capabilities))

    def _offsets_and_sizes_for_volume(self, volume):
        offset = self.model._partition_alignment_data['gpt'].min_start_offset
        for structure in volume.structure:
            if structure.role == snapdapi.Role.MBR:
                continue
            if structure.offset is not None:
                offset = structure.offset
            yield (structure, offset, structure.size)
            offset = offset + structure.size

    async def guided_core_boot(self, disk: Disk):
        # Formatting for a core boot classic system relies on some curtin
        # features that are only available with v2 partitioning.
        await self._mount_systems_dir(self._info.name)
        self.model.storage_version = 2
        [volume] = self._info.system.volumes.values()
        self._on_volume = snapdapi.OnVolume.from_volume(volume)

        preserved_parts = set()

        if self._on_volume.schema != disk.ptable:
            disk.ptable = self._on_volume.schema
            parts_by_offset_size = {}
        else:
            parts_by_offset_size = {
                (part.offset, part.size): part for part in disk.partitions()
                }

            for _struct, offset, size in self._offsets_and_sizes_for_volume(
                    self._on_volume):
                if (offset, size) in parts_by_offset_size:
                    preserved_parts.add(parts_by_offset_size[(offset, size)])

            for part in list(disk.partitions()):
                if part not in preserved_parts:
                    self.delete_partition(part)
                    del parts_by_offset_size[(part.offset, part.size)]

        if not preserved_parts:
            self.reformat(disk, self._on_volume.schema)

        for structure, offset, size in self._offsets_and_sizes_for_volume(
                self._on_volume):
            if (offset, size) in parts_by_offset_size:
                part = parts_by_offset_size[(offset, size)]
            else:
                if structure.role == snapdapi.Role.SYSTEM_DATA and \
                   structure == self._on_volume.structure[-1]:
                    gap = gaps.largest_gap(disk)
                    size = gap.size - (offset - gap.offset)
                part = self.model.add_partition(
                    disk, offset=offset, size=size, check_alignment=False)

            type_uuid = structure.gpt_part_type_uuid()
            if type_uuid:
                part.partition_type = type_uuid
                part.flag = ptable_uuid_to_flag_entry(type_uuid)[0]
            if structure.name:
                part.partition_name = structure.name
            if structure.filesystem:
                part.wipe = 'superblock'
                self.delete_filesystem(part.fs())
                fs = self.model.add_filesystem(
                    part, structure.filesystem, label=structure.label)
                if structure.role == snapdapi.Role.SYSTEM_DATA:
                    self.model.add_mount(fs, '/')
                elif structure.role == snapdapi.Role.SYSTEM_BOOT:
                    self.model.add_mount(fs, '/boot')
                elif part.flag == 'boot':
                    part.grub_device = True
                    self.model.add_mount(fs, '/boot/efi')
            if structure.role != snapdapi.Role.NONE:
                self._role_to_device[structure.role] = part
            self._device_to_structure[part] = structure

        disk._partitions.sort(key=lambda p: p.number)

    def _on_volumes(self) -> Dict[str, snapdapi.OnVolume]:
        # Return a value suitable for use as the 'on-volumes' part of a
        # SystemActionRequest.
        #
        # This must be run after curtin partitioning, which will result in a
        # call to update_devices which will have set .path on all block
        # devices.
        [key] = self._info.system.volumes.keys()
        return {key: self._on_volume}

    @with_context(description="configuring TPM-backed full disk encryption")
    async def setup_encryption(self, context):
        label = self._info.label
        result = await snapdapi.post_and_wait(
            self.app.snapdapi,
            self.app.snapdapi.v2.systems[label].POST,
            snapdapi.SystemActionRequest(
                action=snapdapi.SystemAction.INSTALL,
                step=snapdapi.SystemActionStep.SETUP_STORAGE_ENCRYPTION,
                on_volumes=self._on_volumes()))
        role_to_encrypted_device = result['encrypted-devices']
        for role, enc_path in role_to_encrypted_device.items():
            arb_device = ArbitraryDevice(m=self.model, path=enc_path)
            self.model._actions.append(arb_device)
            part = self._role_to_device[role]
            for fs in self.model._all(type='format'):
                if fs.volume == part:
                    fs.volume = arb_device

    @with_context(description="making system bootable")
    async def finish_install(self, context):
        label = self._info.label
        await snapdapi.post_and_wait(
            self.app.snapdapi,
            self.app.snapdapi.v2.systems[label].POST,
            snapdapi.SystemActionRequest(
                action=snapdapi.SystemAction.INSTALL,
                step=snapdapi.SystemActionStep.FINISH,
                on_volumes=self._on_volumes()))

    async def guided_POST(self, data: GuidedChoice) -> StorageResponse:
        log.debug(data)
        await self.guided(GuidedChoiceV2.from_guided_choice(data))
        if data.capability.is_core_boot():
            await self.configured()
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
        catalog_entry = self.app.base_model.source.current
        source_min = max(
            variation.size
            for variation in catalog_entry.variations.values()
            )
        align = max((pa.part_align
                     for pa in self.model._partition_alignment_data.values()))
        return sizes.calculate_suggested_install_min(source_min, align)

    async def get_v2_storage_response(self, model, wait):
        probe_resp = await self._probe_response(wait, StorageResponseV2)
        if probe_resp is not None:
            return probe_resp
        disks = [
            d for d in model._all(type='disk') if d not in model._exclusions
            ]
        minsize = self.calculate_suggested_install_min()
        return StorageResponseV2(
                status=ProbeStatus.DONE,
                disks=[labels.for_client(d) for d in disks],
                need_root=not model.is_root_mounted(),
                need_boot=model.needs_bootloader_partition(),
                install_minimum_size=minsize,
                )

    async def v2_GET(self, wait: bool = False) -> StorageResponseV2:
        return await self.get_v2_storage_response(self.model, wait)

    async def v2_POST(self) -> StorageResponseV2:
        await self.configured()
        return await self.v2_GET()

    async def v2_orig_config_GET(self) -> StorageResponseV2:
        model = self.model.get_orig_model()
        return await self.get_v2_storage_response(model, False)

    async def v2_reset_POST(self) -> StorageResponseV2:
        log.info("Resetting Filesystem model")
        # From the API standpoint, it seems sound to set locked_probe_data back
        # to False after a reset. But in practise, v2_reset_POST can be called
        # during manual partitioning ; and we don't want to reenable automatic
        # loading of probe data. Going forward, this could be controlled by an
        # optional parameter maybe?
        if self.queued_probe_data is not None:
            log.debug("using newly obtained probe data")
            self.model.load_probe_data(self.queued_probe_data)
            self.queued_probe_data = None
        else:
            self.model.reset()
        return await self.v2_GET()

    async def v2_ensure_transaction_POST(self) -> None:
        self.locked_probe_data = True

    def get_available_capabilities(self):
        classic_capabilities = set()
        core_boot_capabilities = set()
        for info in self._variation_info.values():
            if not info.is_valid():
                continue
            if info.is_core_boot_classic():
                core_boot_capabilities.update(info.capabilities)
            else:
                classic_capabilities.update(info.capabilities)
        return sorted(classic_capabilities, key=lambda x: x.name), \
            sorted(core_boot_capabilities, key=lambda x: x.name)

    async def v2_guided_GET(self, wait: bool = False) \
            -> GuidedStorageResponseV2:
        """Acquire a list of possible guided storage configuration scenarios.
        Results are sorted by the size of the space potentially available to
        the install."""
        probe_resp = await self._probe_response(wait, GuidedStorageResponseV2)
        if probe_resp is not None:
            return probe_resp

        scenarios = []
        install_min = self.calculate_suggested_install_min()

        classic_capabilities, core_boot_capabilities = \
            self.get_available_capabilities()

        for disk in self.potential_boot_disks(with_reformatting=True):
            if disk.size >= install_min:
                reformat = GuidedStorageTargetReformat(
                    disk_id=disk.id,
                    capabilities=core_boot_capabilities + classic_capabilities)
                scenarios.append((disk.size, reformat))

        for disk in self.potential_boot_disks(with_reformatting=False):
            if len(disk.partitions()) < 1:
                # On an empty disk, don't bother to offer it with UseGap, as
                # it's basically the same as the Reformat case.
                continue
            gap = gaps.largest_gap(disk)
            if gap is not None and gap.size >= install_min:
                api_gap = labels.for_client(gap)
                use_gap = GuidedStorageTargetUseGap(
                    disk_id=disk.id, gap=api_gap,
                    capabilities=classic_capabilities)
                scenarios.append((gap.size, use_gap))

        for disk in self.potential_boot_disks(check_boot=False):
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
                    partition, vals, capabilities=classic_capabilities)
                scenarios.append((vals.install_max, resize))

        scenarios.sort(reverse=True, key=lambda x: x[0])
        return GuidedStorageResponseV2(
                status=ProbeStatus.DONE,
                configured=self.model.guided_configuration,
                possible=[s[1] for s in scenarios if s[1].capabilities])

    async def v2_guided_POST(self, data: GuidedChoiceV2) \
            -> GuidedStorageResponseV2:
        log.debug(data)
        self.locked_probe_data = True
        await self.guided(data)
        return await self.v2_guided_GET()

    async def v2_reformat_disk_POST(self, data: ReformatDisk) \
            -> StorageResponseV2:
        self.locked_probe_data = True
        self.reformat(self.model._one(id=data.disk_id), data.ptable)
        return await self.v2_GET()

    async def v2_add_boot_partition_POST(self, disk_id: str) \
            -> StorageResponseV2:
        self.locked_probe_data = True
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
        self.locked_probe_data = True
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
        self.locked_probe_data = True
        disk = self.model._one(id=data.disk_id)
        partition = self.get_partition(disk, data.partition.number)
        self.delete_partition(partition)
        return await self.v2_GET()

    async def v2_edit_partition_POST(self, data: ModifyPartitionV2) \
            -> StorageResponseV2:
        log.debug(data)
        self.locked_probe_data = True
        disk = self.model._one(id=data.disk_id)
        partition = self.get_partition(disk, data.partition.number)
        if data.partition.size not in (None, partition.size) \
                and self.app.opts.storage_version < 2:
            raise ValueError('edit_partition does not support changing size')
        if data.partition.boot is not None \
                and data.partition.boot != partition.boot:
            raise ValueError('edit_partition does not support changing boot')
        spec = {'mount': data.partition.mount or partition.mount}
        if data.partition.format is not None:
            if data.partition.format != partition.original_fstype():
                if data.partition.wipe is None:
                    raise ValueError(
                        'changing partition format requires a wipe value')
            spec['fstype'] = data.partition.format
        if data.partition.size is not None:
            spec['size'] = data.partition.size
        spec['wipe'] = data.partition.wipe
        self.partition_disk_handler(disk, spec, partition=partition)
        return await self.v2_GET()

    async def dry_run_wait_probe_POST(self) -> None:
        if not self.app.opts.dry_run:
            raise NotImplementedError

        # This will start the probe task if not yet started.
        self.ensure_probing()

        await self._probe_task.task

    @with_context(name='probe_once', description='restricted={restricted}')
    async def _probe_once(self, *, context, restricted):
        if restricted:
            probe_types = {'blockdev', 'filesystem'}
            fname = 'probe-data-restricted.json'
            key = "ProbeDataRestricted"
        else:
            probe_types = {'defaults', 'filesystem_sizing'}
            if self.app.opts.use_os_prober:
                probe_types |= {'os'}
            fname = 'probe-data.json'
            key = "ProbeData"
        storage = await self.app.prober.get_storage(probe_types)
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
        if not self.locked_probe_data:
            self.queued_probe_data = None
            self.model.load_probe_data(storage)
        else:
            self.queued_probe_data = storage

    @with_context()
    async def _probe(self, *, context=None):
        self._errors = {}
        for (restricted, kind, short_label) in [
                (False, ErrorReportKind.BLOCK_PROBE_FAIL, "block"),
                (True,  ErrorReportKind.DISK_PROBE_FAIL, "disk"),
                ]:
            try:
                start = time.time()
                await self._probe_once_task.start(
                    context=context, restricted=restricted)
                # We wait on the task directly here, not
                # self._probe_once_task.wait as if _probe_once_task
                # gets cancelled, we should be cancelled too.
                await asyncio.wait_for(self._probe_once_task.task, 90.0)
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
            finally:
                elapsed = time.time() - start
                log.debug(f'{short_label} probing took {elapsed:.1f} seconds')
            break

    async def run_autoinstall_guided(self, layout):
        name = layout['name']
        password = None
        sizing_policy = None

        if name == 'hybrid':
            # this check is conceptually unnecessary but results in a
            # much cleaner error message...
            for variation in self._variation_info.values():
                if not variation.is_valid():
                    continue
                if variation.is_core_boot_classic():
                    break
            else:
                raise Exception(
                    "can only use name: hybrid when installing core boot "
                    "classic")
            if 'mode' in layout:
                raise Exception(
                    "cannot use 'mode' when installing core boot classic")
            encrypted = layout.get('encrypted', None)
            GC = GuidedCapability
            if encrypted is None:
                if GC.CORE_BOOT_ENCRYPTED in self._info.capabilities or \
                   GC.CORE_BOOT_PREFER_ENCRYPTED in self._info.capabilities:
                    capability = GC.CORE_BOOT_ENCRYPTED
                else:
                    capability = GC.CORE_BOOT_UNENCRYPTED
            elif encrypted:
                capability = GC.CORE_BOOT_ENCRYPTED
            else:
                if self._info.capabilities == {
                        GuidedCapability.CORE_BOOT_ENCRYPTED} and \
                   not encrypted:
                    raise Exception("cannot install this model unencrypted")
                capability = GC.CORE_BOOT_UNENCRYPTED
            match = layout.get("match", {'size': 'largest'})
            disk = self.model.disk_for_match(self.model.all_disks(), match)
            mode = 'reformat_disk'
        else:
            # this check is conceptually unnecessary but results in a
            # much cleaner error message...
            for variation in self._variation_info.values():
                if not variation.is_valid():
                    continue
                if not variation.is_core_boot_classic():
                    break
            else:
                raise Exception(
                    "must use name: hybrid when installing core boot "
                    "classic")
            mode = layout.get('mode', 'reformat_disk')
            self.validate_layout_mode(mode)
            password = layout.get('password', None)
            if name == 'lvm':
                sizing_policy = SizingPolicy.from_string(
                        layout.get('sizing-policy', None))
                if password is not None:
                    capability = GuidedCapability.LVM_LUKS
                else:
                    capability = GuidedCapability.LVM
            else:
                capability = GuidedCapability.DIRECT

        if mode == 'reformat_disk':
            match = layout.get("match", {'size': 'largest'})
            disk = self.model.disk_for_match(self.model.all_disks(), match)
            target = GuidedStorageTargetReformat(
                disk_id=disk.id, capabilities=[])
        elif mode == 'use_gap':
            bootable = [d for d in self.model.all_disks()
                        if boot.can_be_boot_device(d, with_reformatting=False)]
            gap = gaps.largest_gap(bootable)
            if not gap:
                raise Exception("autoinstall cannot configure storage "
                                "- no gap found large enough for install")
            target = GuidedStorageTargetUseGap(
                disk_id=gap.device.id, gap=gap, capabilities=[])

        log.info(f'autoinstall: running guided {capability} install in '
                 f'mode {mode} using {target}')
        await self.guided(
                GuidedChoiceV2(target=target, capability=capability,
                               password=password, sizing_policy=sizing_policy))

    def validate_layout_mode(self, mode):
        if mode not in ('reformat_disk', 'use_gap'):
            raise ValueError(f'Unknown layout mode {mode}')

    @with_context()
    async def convert_autoinstall_config(self, context=None):
        # Log disabled to prevent LUKS password leak
        # log.debug("self.ai_data = %s", self.ai_data)
        if 'layout' in self.ai_data:
            if 'config' in self.ai_data:
                log.warning("The 'storage' section should not contain both "
                            "'layout' and 'config', using 'layout'")
            await self.run_autoinstall_guided(self.ai_data['layout'])
        elif 'config' in self.ai_data:
            # XXX in principle should there be a way to influence the
            # variation chosen here? Not with current use cases for
            # variations anyway.
            for variation in self._variation_info.values():
                if not variation.is_valid():
                    continue
                if not variation.is_core_boot_classic():
                    self._info = variation
                    break
            else:
                raise Exception(
                    "must not use config: when installing core boot classic")
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
        loop = asyncio.get_running_loop()
        loop.add_reader(self._monitor.fileno(), self._udev_event)

    def stop_listening_udev(self):
        loop = asyncio.get_running_loop()
        loop.remove_reader(self._monitor.fileno())

    def ensure_probing(self):
        try:
            self._probe_task.start_sync()
        except TaskAlreadyRunningError:
            log.debug('Skipping run of Probert - probe run already active')
        else:
            log.debug('Triggered Probert run on udev event')

    def _udev_event(self):
        cp = run_command(['udevadm', 'settle', '-t', '0'])
        if cp.returncode != 0:
            log.debug("waiting 0.1 to let udev event queue settle")
            self.stop_listening_udev()
            loop = asyncio.get_running_loop()
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
        self.ensure_probing()

    def make_autoinstall(self):
        rendered = self.model.render()
        r = {
            'config': rendered['storage']['config']
            }
        if 'swap' in rendered:
            r['swap'] = rendered['swap']
        return r
