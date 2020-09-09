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
from subiquitycore.lsb_release import lsb_release
from subiquitycore.utils import (
    run_command,
    )


from subiquity.common.errorreport import ErrorReportKind
from subiquity.controller import SubiquityTuiController
from subiquity.models.filesystem import (
    align_up,
    Bootloader,
    DeviceAction,
    dehumanize_size,
    Partition,
    raidlevels_by_value,
    )
from subiquity.ui.views import (
    FilesystemView,
    GuidedDiskSelectionView,
    )
from subiquity.ui.views.filesystem.probing import (
    SlowProbing,
    ProbingFailed,
    )


log = logging.getLogger("subiquitycore.controller.filesystem")
block_discover_log = logging.getLogger('block-discover')

BIOS_GRUB_SIZE_BYTES = 1 * 1024 * 1024    # 1MiB
PREP_GRUB_SIZE_BYTES = 8 * 1024 * 1024    # 8MiB
UEFI_GRUB_SIZE_BYTES = 512 * 1024 * 1024  # 512MiB EFI partition


class FilesystemController(SubiquityTuiController):

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
        self.answers.setdefault('guided', False)
        self.answers.setdefault('guided-index', 0)
        self.answers.setdefault('manual', [])
        self._monitor = None
        self._crash_reports = {}
        self._probe_once_task = SingleInstanceTask(
            self._probe_once, propagate_errors=False)
        self._probe_task = SingleInstanceTask(
            self._probe, propagate_errors=False)
        if self.model.bootloader == Bootloader.PREP:
            self.supports_resilient_boot = False
        else:
            release = lsb_release()['release']
            self.supports_resilient_boot = release >= '20.04'

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
        self.stop_listening_udev()
        await self._start_task
        await self._probe_task.wait()
        self.convert_autoinstall_config(context=context)
        if not self.model.is_root_mounted():
            raise Exception("autoinstall config did not mount root")
        if self.model.needs_bootloader_partition():
            raise Exception(
                "autoinstall config did not create needed bootloader "
                "partition")

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
        async with self.app.install_lock_file.shared():
            self._crash_reports = {}
            if isinstance(self.ui.body, ProbingFailed):
                self.ui.set_body(SlowProbing(self))
                schedule_task(self._wait_for_probing())
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
                    report = self.app.make_apport_report(
                        kind, "block probing", interrupt=False)
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

    async def _wait_for_probing(self):
        await self._start_task
        await self._probe_task.wait()
        if isinstance(self.ui.body, SlowProbing):
            self.start_ui()

    def start_ui(self):
        if self._probe_task.task is None or not self._probe_task.task.done():
            self.ui.set_body(SlowProbing(self))
            schedule_task(self._wait_for_probing())
        elif True in self._crash_reports:
            self.ui.set_body(ProbingFailed(self))
            self.ui.body.show_error()
        else:
            # Once we've shown the filesystem UI, we stop listening for udev
            # events as merging system changes with configuration the user has
            # performed would be tricky.  Possibly worth doing though! Just
            # not today.
            self.convert_autoinstall_config()
            self.stop_listening_udev()
            self.ui.set_body(GuidedDiskSelectionView(self))
            pr = self._crash_reports.get(False)
            if pr is not None:
                self.app.show_error_report(pr)
            if self.answers['guided']:
                disk = self.model.all_disks()[self.answers['guided-index']]
                method = self.answers.get('guided-method')
                self.ui.body.form.guided_choice.value = {
                    'disk': disk,
                    'use_lvm': method == "lvm",
                    }
                self.ui.body.done(self.ui.body.form)
            elif self.answers['manual']:
                self.manual()

    def _action_get(self, id):
        dev_spec = id[0].split()
        dev = None
        if dev_spec[0] == "disk":
            if dev_spec[1] == "index":
                dev = self.model.all_disks()[int(dev_spec[2])]
            elif dev_spec[1] == "serial":
                dev = self.model._one(type='disk', serial=dev_spec[2])
        elif dev_spec[0] == "raid":
            if dev_spec[1] == "name":
                for r in self.model.all_raids():
                    if r.name == dev_spec[2]:
                        dev = r
                        break
        elif dev_spec[0] == "volgroup":
            if dev_spec[1] == "name":
                for r in self.model.all_volgroups():
                    if r.name == dev_spec[2]:
                        dev = r
                        break
        if dev is None:
            raise Exception("could not resolve {}".format(id))
        if len(id) > 1:
            part, index = id[1].split()
            if part == "part":
                return dev.partitions()[int(index)]
        else:
            return dev
        raise Exception("could not resolve {}".format(id))

    def _action_clean_devices_raid(self, devices):
        r = {
            self._action_get(d): v
            for d, v in zip(devices[::2], devices[1::2])
            }
        for d in r:
            assert d.ok_for_raid
        return r

    def _action_clean_devices_vg(self, devices):
        r = {self._action_get(d): 'active' for d in devices}
        for d in r:
            assert d.ok_for_lvm_vg
        return r

    def _action_clean_level(self, level):
        return raidlevels_by_value[level]

    def _answers_action(self, action):
        from subiquitycore.ui.stretchy import StretchyOverlay
        from subiquity.ui.views.filesystem.delete import ConfirmDeleteStretchy
        log.debug("_answers_action %r", action)
        if 'obj' in action:
            obj = self._action_get(action['obj'])
            action_name = action['action']
            if action_name == "MAKE_BOOT":
                action_name = "TOGGLE_BOOT"
            meth = getattr(
                self.ui.body.avail_list,
                "_{}_{}".format(obj.type, action_name))
            meth(obj)
            yield
            body = self.ui.body._w
            if not isinstance(body, StretchyOverlay):
                return
            if isinstance(body.stretchy, ConfirmDeleteStretchy):
                if action.get("submit", True):
                    body.stretchy.done()
            else:
                yield from self._enter_form_data(
                    body.stretchy.form,
                    action['data'],
                    action.get("submit", True))
        elif action['action'] == 'create-raid':
            self.ui.body.create_raid()
            yield
            body = self.ui.body._w
            yield from self._enter_form_data(
                body.stretchy.form,
                action['data'],
                action.get("submit", True),
                clean_suffix='raid')
        elif action['action'] == 'create-vg':
            self.ui.body.create_vg()
            yield
            body = self.ui.body._w
            yield from self._enter_form_data(
                body.stretchy.form,
                action['data'],
                action.get("submit", True),
                clean_suffix='vg')
        elif action['action'] == 'done':
            if not self.ui.body.done.enabled:
                raise Exception("answers did not provide complete fs config")
            self.app.confirm_install()
            self.finish()
        else:
            raise Exception("could not process action {}".format(action))

    def manual(self):
        self.ui.set_body(FilesystemView(self.model, self))
        if self.answers['guided']:
            self.app.confirm_install()
            self.finish()
        if self.answers['manual']:
            self._run_iterator(self._run_actions(self.answers['manual']))
            self.answers['manual'] = []

    def guided(self, method):
        v = GuidedDiskSelectionView(self.model, self, method)
        self.ui.set_body(v)
        if self.answers['guided']:
            index = self.answers['guided-index']
            v.form.guided.value = True
            v.form.guided_choice.disk.widget.index = index
            v.form._emit('done')

    def reset(self):
        log.info("Resetting Filesystem model")
        self.model.reset()
        self.manual()

    def cancel(self):
        self.app.prev_screen()

    def finish(self):
        log.debug("FilesystemController.finish next_screen")
        self.configured()
        self.app.next_screen()

    def create_mount(self, fs, spec):
        if spec.get('mount') is None:
            return
        mount = self.model.add_mount(fs, spec['mount'])
        if self.model.needs_bootloader_partition():
            vol = fs.volume
            if vol.type == "partition" and vol.device.type == "disk":
                if vol.device._can_be_boot_disk():
                    self.add_boot_disk(vol.device)
        return mount

    def delete_mount(self, mount):
        if mount is None:
            return
        self.model.remove_mount(mount)

    def create_filesystem(self, volume, spec):
        if spec['fstype'] is None:
            # prep partitions are always wiped (and never have a filesystem)
            if getattr(volume, 'flag', None) != 'prep':
                volume.wipe = None
            fstype = volume.original_fstype()
            if fstype is None:
                return None
            preserve = True
        else:
            fstype = spec['fstype']
            volume.wipe = 'superblock'
            preserve = False
        fs = self.model.add_filesystem(volume, fstype, preserve)
        if isinstance(volume, Partition):
            if fstype == "swap":
                volume.flag = "swap"
            elif volume.flag == "swap":
                volume.flag = ""
        if spec['fstype'] == "swap":
            self.model.add_mount(fs, "")
        if spec['fstype'] is None and spec['use_swap']:
            self.model.add_mount(fs, "")
        self.create_mount(fs, spec)
        return fs

    def delete_filesystem(self, fs):
        if fs is None:
            return
        self.delete_mount(fs.mount())
        self.model.remove_filesystem(fs)
    delete_format = delete_filesystem

    def create_partition(self, device, spec, flag="", wipe=None,
                         grub_device=None):
        part = self.model.add_partition(
            device, spec["size"], flag, wipe, grub_device)
        self.create_filesystem(part, spec)
        return part

    def delete_partition(self, part):
        self.clear(part)
        self.model.remove_partition(part)

    def _create_boot_partition(self, disk):
        bootloader = self.model.bootloader
        if bootloader == Bootloader.UEFI:
            part_size = UEFI_GRUB_SIZE_BYTES
            if UEFI_GRUB_SIZE_BYTES*2 >= disk.size:
                part_size = disk.size // 2
            log.debug('_create_boot_partition - adding EFI partition')
            spec = dict(size=part_size, fstype='fat32')
            if self.model._mount_for_path("/boot/efi") is None:
                spec['mount'] = '/boot/efi'
            part = self.create_partition(
                disk, spec, flag="boot", grub_device=True)
        elif bootloader == Bootloader.PREP:
            log.debug('_create_boot_partition - adding PReP partition')
            part = self.create_partition(
                disk,
                dict(size=PREP_GRUB_SIZE_BYTES, fstype=None, mount=None),
                # must be wiped or grub-install will fail
                wipe='zero',
                flag='prep', grub_device=True)
        elif bootloader == Bootloader.BIOS:
            log.debug('_create_boot_partition - adding bios_grub partition')
            part = self.create_partition(
                disk,
                dict(size=BIOS_GRUB_SIZE_BYTES, fstype=None, mount=None),
                flag='bios_grub')
            disk.grub_device = True
        return part

    def create_raid(self, spec):
        for d in spec['devices'] | spec['spare_devices']:
            self.clear(d)
        raid = self.model.add_raid(
            spec['name'],
            spec['level'].value,
            spec['devices'],
            spec['spare_devices'])
        return raid

    def delete_raid(self, raid):
        if raid is None:
            return
        self.clear(raid)
        for p in list(raid.partitions()):
            self.delete_partition(p)
        for d in set(raid.devices) | set(raid.spare_devices):
            d.wipe = 'superblock'
        self.model.remove_raid(raid)

    def create_volgroup(self, spec):
        devices = set()
        key = spec.get('password')
        for device in spec['devices']:
            self.clear(device)
            if key:
                device = self.model.add_dm_crypt(device, key)
            devices.add(device)
        return self.model.add_volgroup(name=spec['name'], devices=devices)
    create_lvm_volgroup = create_volgroup

    def delete_volgroup(self, vg):
        for lv in list(vg.partitions()):
            self.delete_logical_volume(lv)
        for d in vg.devices:
            d.wipe = 'superblock'
            if d.type == "dm_crypt":
                self.model.remove_dm_crypt(d)
        self.model.remove_volgroup(vg)
    delete_lvm_volgroup = delete_volgroup

    def create_logical_volume(self, vg, spec):
        lv = self.model.add_logical_volume(
            vg=vg,
            name=spec['name'],
            size=spec['size'])
        self.create_filesystem(lv, spec)
        return lv
    create_lvm_partition = create_logical_volume

    def delete_logical_volume(self, lv):
        self.clear(lv)
        self.model.remove_logical_volume(lv)
    delete_lvm_partition = delete_logical_volume

    def delete(self, obj):
        if obj is None:
            return
        getattr(self, 'delete_' + obj.type)(obj)

    def clear(self, obj):
        if obj.type == "disk":
            obj.preserve = False
        obj.wipe = 'superblock'
        for subobj in obj.fs(), obj.constructed_device():
            self.delete(subobj)

    def reformat(self, disk):
        disk.grub_device = False
        for p in list(disk.partitions()):
            self.delete_partition(p)
        self.clear(disk)

    def partition_disk_handler(self, disk, partition, spec):
        log.debug('partition_disk_handler: %s %s %s', disk, partition, spec)
        log.debug('disk.freespace: {}'.format(disk.free_for_partitions))

        if partition is not None:
            if 'size' in spec:
                partition.size = align_up(spec['size'])
                if disk.free_for_partitions < 0:
                    raise Exception("partition size too large")
            self.delete_filesystem(partition.fs())
            self.create_filesystem(partition, spec)
            return

        if len(disk.partitions()) == 0:
            if disk.type == "disk":
                disk.preserve = False
                disk.wipe = 'superblock-recursive'

        needs_boot = self.model.needs_bootloader_partition()
        log.debug('model needs a bootloader partition? {}'.format(needs_boot))
        can_be_boot = DeviceAction.TOGGLE_BOOT in disk.supported_actions
        if needs_boot and len(disk.partitions()) == 0 and can_be_boot:
            part = self._create_boot_partition(disk)

            # adjust downward the partition size (if necessary) to accommodate
            # bios/grub partition
            if spec['size'] > disk.free_for_partitions:
                log.debug(
                    "Adjusting request down: %s - %s = %s",
                    spec['size'], part.size, disk.free_for_partitions)
                spec['size'] = disk.free_for_partitions

        self.create_partition(disk, spec)

        log.debug("Successfully added partition")

    def logical_volume_handler(self, vg, lv, spec):
        log.debug('logical_volume_handler: %s %s %s', vg, lv, spec)
        log.debug('vg.freespace: {}'.format(vg.free_for_partitions))

        if lv is not None:
            if 'name' in spec:
                lv.name = spec['name']
            if 'size' in spec:
                lv.size = align_up(spec['size'])
                if vg.free_for_partitions < 0:
                    raise Exception("lv size too large")
            self.delete_filesystem(lv.fs())
            self.create_filesystem(lv, spec)
            return

        self.create_logical_volume(vg, spec)

    def add_format_handler(self, volume, spec):
        log.debug('add_format_handler %s %s', volume, spec)
        self.clear(volume)
        self.create_filesystem(volume, spec)

    def raid_handler(self, existing, spec):
        log.debug("raid_handler %s %s", existing, spec)
        if existing is not None:
            for d in existing.devices | existing.spare_devices:
                d._constructed_device = None
            for d in spec['devices'] | spec['spare_devices']:
                self.clear(d)
                d._constructed_device = existing
            existing.name = spec['name']
            existing.raidlevel = spec['level'].value
            existing.devices = spec['devices']
            existing.spare_devices = spec['spare_devices']
        else:
            self.create_raid(spec)

    def volgroup_handler(self, existing, spec):
        if existing is not None:
            key = spec.get('password')
            for d in existing.devices:
                if d.type == "dm_crypt":
                    self.model.remove_dm_crypt(d)
                    d = d.volume
                d._constructed_device = None
            devices = set()
            for d in spec['devices']:
                self.clear(d)
                if key:
                    d = self.model.add_dm_crypt(d, key)
                d._constructed_device = existing
                devices.add(d)
            existing.name = spec['name']
            existing.devices = devices
        else:
            self.create_volgroup(spec)

    def _mount_esp(self, part):
        if part.fs() is None:
            self.model.add_filesystem(part, 'fat32')
        self.model.add_mount(part.fs(), '/boot/efi')

    def remove_boot_disk(self, boot_disk):
        if self.model.bootloader == Bootloader.BIOS:
            boot_disk.grub_device = False
        partitions = [
            p for p in boot_disk.partitions()
            if p.is_bootloader_partition
            ]
        remount = False
        if boot_disk.preserve:
            if self.model.bootloader == Bootloader.BIOS:
                return
            for p in partitions:
                p.grub_device = False
                if self.model.bootloader == Bootloader.PREP:
                    p.wipe = None
                elif self.model.bootloader == Bootloader.UEFI:
                    if p.fs():
                        if p.fs().mount():
                            self.delete_mount(p.fs().mount())
                            remount = True
                        if not p.fs().preserve and p.original_fstype():
                            self.delete_filesystem(p.fs())
                            self.model.add_filesystem(
                                p, p.original_fstype(), preserve=True)
        else:
            full = boot_disk.free_for_partitions == 0
            tot_size = 0
            for p in partitions:
                tot_size += p.size
                if p.fs() and p.fs().mount():
                    remount = True
                self.delete_partition(p)
            if full:
                largest_part = max(
                    boot_disk.partitions(), key=lambda p: p.size)
                largest_part.size += tot_size
        if self.model.bootloader == Bootloader.UEFI and remount:
            part = self.model._one(type='partition', grub_device=True)
            if part:
                self._mount_esp(part)

    def add_boot_disk(self, new_boot_disk):
        bootloader = self.model.bootloader
        if not self.supports_resilient_boot:
            for disk in self.model.all_disks():
                if disk._is_boot_device():
                    self.remove_boot_disk(disk)
        if new_boot_disk._has_preexisting_partition():
            if bootloader == Bootloader.BIOS:
                new_boot_disk.grub_device = True
            elif bootloader == Bootloader.UEFI:
                should_mount = self.model._mount_for_path('/boot/efi') is None
                for p in new_boot_disk.partitions():
                    if p.is_esp:
                        p.grub_device = True
                        if should_mount:
                            self._mount_esp(p)
                            should_mount = False
            elif bootloader == Bootloader.PREP:
                for p in new_boot_disk.partitions():
                    if p.flag == 'prep':
                        p.wipe = 'zero'
                        p.grub_device = True
        else:
            new_boot_disk.preserve = False
            if bootloader == Bootloader.UEFI:
                part_size = UEFI_GRUB_SIZE_BYTES
                if UEFI_GRUB_SIZE_BYTES*2 >= new_boot_disk.size:
                    part_size = new_boot_disk.size // 2
            elif bootloader == Bootloader.PREP:
                part_size = PREP_GRUB_SIZE_BYTES
            elif bootloader == Bootloader.BIOS:
                part_size = BIOS_GRUB_SIZE_BYTES
            if part_size > new_boot_disk.free_for_partitions:
                largest_part = max(
                    new_boot_disk.partitions(), key=lambda p: p.size)
                largest_part.size -= (
                    part_size - new_boot_disk.free_for_partitions)
            self._create_boot_partition(new_boot_disk)

    def guided_direct(self, disk):
        self.reformat(disk)
        result = {
            "size": disk.free_for_partitions,
            "fstype": "ext4",
            "mount": "/",
            }
        self.partition_disk_handler(disk, None, result)

    def guided_lvm(self, disk, lvm_options=None):
        self.reformat(disk)
        if DeviceAction.TOGGLE_BOOT in disk.supported_actions:
            self.add_boot_disk(disk)
        self.create_partition(
            device=disk, spec=dict(
                size=dehumanize_size('1G'),
                fstype="ext4",
                mount='/boot'
                ))
        part = self.create_partition(
            device=disk, spec=dict(
                size=disk.free_for_partitions,
                fstype=None,
                ))
        spec = dict(name="ubuntu-vg", devices=set([part]))
        if lvm_options and lvm_options['encrypt']:
            spec['password'] = lvm_options['luks_options']['password']
        vg = self.create_volgroup(spec)
        # There's no point using LVM and unconditionally filling the
        # VG with a single LV, but we should use more of a smaller
        # disk to avoid the user running into out of space errors
        # earlier than they probably expect to.
        if vg.size < 10 * (2 << 30):
            # Use all of a small (<10G) disk.
            lv_size = vg.size
        elif vg.size < 20 * (2 << 30):
            # Use 10G of a smallish (<20G) disk.
            lv_size = 10 * (2 << 30)
        elif vg.size < 200 * (2 << 30):
            # Use half of a larger (<200G) disk.
            lv_size = vg.size // 2
        else:
            # Use at most 100G of a large disk.
            lv_size = 100 * (2 << 30)
        self.create_logical_volume(
            vg=vg, spec=dict(
                size=lv_size,
                name="ubuntu-lv",
                fstype="ext4",
                mount="/",
                ))

    def make_autoinstall(self):
        rendered = self.model.render()
        r = {
            'config': rendered['storage']['config']
            }
        if 'swap' in rendered:
            r['swap'] = rendered['swap']
        return r
