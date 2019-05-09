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

import enum
import logging
import os
import platform

from probert.storage import StorageInfo

from subiquitycore.controller import BaseController

from subiquity.models.filesystem import (
    align_up,
    DeviceAction,
    Partition,
    raidlevels_by_value,
    )
from subiquity.ui.views import (
    FilesystemView,
    GuidedDiskSelectionView,
    GuidedFilesystemView,
    )
from subiquity.ui.views.filesystem.probing import (
    SlowProbing,
    ProbingFailed,
    )


log = logging.getLogger("subiquitycore.controller.filesystem")

BIOS_GRUB_SIZE_BYTES = 1 * 1024 * 1024    # 1MiB
PREP_GRUB_SIZE_BYTES = 8 * 1024 * 1024    # 8MiB
UEFI_GRUB_SIZE_BYTES = 512 * 1024 * 1024  # 512MiB EFI partition


class ProbeState(enum.IntEnum):
    NOT_STARTED = enum.auto()
    PROBING = enum.auto()
    REPROBING = enum.auto()
    FAILED = enum.auto()
    DONE = enum.auto()


class FilesystemController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.filesystem
        self.answers = self.all_answers.get("Filesystem", {})
        self.answers.setdefault('guided', False)
        self.answers.setdefault('guided-index', 0)
        self.answers.setdefault('manual', [])
        self.showing = False
        self._probe_state = ProbeState.NOT_STARTED

    def start(self):
        self._probe_state = ProbeState.PROBING
        self.run_in_bg(self._bg_probe, self._probed)
        self.loop.set_alarm_in(
            5.0, lambda loop, ud: self._check_probe_timeout())

    def _bg_probe(self, probe_types=None):
        probed_data = self.prober.get_storage(probe_types=probe_types)
        storage = {}
        for path, data in probed_data["blockdev"].items():
            storage[path] = StorageInfo({path: data})
        return storage

    def _probed(self, fut, restricted=False):
        if not restricted and self._probe_state != ProbeState.PROBING:
            log.debug("ignoring result %s for timed out probe", fut)
            return
        try:
            storage = fut.result()
        except Exception:
            log.exception("probing failed restricted=%s", restricted)
            if not restricted:
                log.info("reprobing for blockdev only")
                # Should make a crash file for apport, arrange for it to be
                # copied onto the installed system and tell user all this
                # happened!
                self._reprobe()
            else:
                self._probe_state = ProbeState.FAILED
                if self.showing:
                    self.default()
        else:
            self.model.load_probe_data(storage)
            self._probe_state = ProbeState.DONE
            # Should do something here if probing found no devices.
            if self.showing:
                self.default()

    def _check_probe_timeout(self):
        log.debug("_check_probe_timeout")
        if self._probe_state == ProbeState.PROBING:
            log.info(
                "unrestricted probing timed out, reprobing for blockdev only")
            self._reprobe()

    def _reprobe(self):
        self._probe_state = ProbeState.REPROBING
        self.run_in_bg(
            lambda: self._bg_probe(["blockdev"]),
            lambda fut: self._probed(fut, True),
            )

    def default(self):
        self.showing = True
        if self._probe_state in [ProbeState.PROBING,
                                 ProbeState.REPROBING]:
            self.ui.set_body(SlowProbing(self))
        elif self._probe_state == ProbeState.FAILED:
            self.ui.set_body(ProbingFailed(self))
        else:
            self.ui.set_body(GuidedFilesystemView(self))
            if self.answers['guided']:
                self.guided(self.answers.get('guided-method', 'direct'))
            elif self.answers['manual']:
                self.manual()

    def _action_get(self, id):
        dev_spec = id[0].split()
        dev = None
        if dev_spec[0] == "disk":
            if dev_spec[1] == "index":
                dev = self.model.all_disks()[int(dev_spec[2])]
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

    def _action_clean_fstype(self, fstype):
        return self.model.fs_by_name[fstype]

    def _action_clean_devices_raid(self, devices):
        return {
            self._action_get(d): v
            for d, v in zip(devices[::2], devices[1::2])
            }

    def _action_clean_devices_vg(self, devices):
        return {self._action_get(d): 'active' for d in devices}

    def _action_clean_level(self, level):
        if isinstance(level, int):
            level = "raid" + str(level)
        return raidlevels_by_value[level]

    def _answers_action(self, action):
        from subiquitycore.ui.stretchy import StretchyOverlay
        from subiquity.ui.views.filesystem.delete import ConfirmDeleteStretchy
        log.debug("_answers_action %r", action)
        if 'obj' in action:
            obj = self._action_get(action['obj'])
            meth = getattr(
                self.ui.frame.body.avail_list,
                "_{}_{}".format(obj.type, action['action']))
            meth(obj)
            yield
            body = self.ui.frame.body._w
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
            self.ui.frame.body.create_raid()
            yield
            body = self.ui.frame.body._w
            yield from self._enter_form_data(
                body.stretchy.form,
                action['data'],
                action.get("submit", True),
                clean_suffix='raid')
        elif action['action'] == 'create-vg':
            self.ui.frame.body.create_vg()
            yield
            body = self.ui.frame.body._w
            yield from self._enter_form_data(
                body.stretchy.form,
                action['data'],
                action.get("submit", True),
                clean_suffix='vg')
        elif action['action'] == 'done':
            if not self.ui.frame.body.done.enabled:
                raise Exception("answers did not provide complete fs config")
            self.finish()
        else:
            raise Exception("could not process action {}".format(action))

    def manual(self):
        self.ui.set_body(FilesystemView(self.model, self))
        if self.answers['guided']:
            self.finish()
        if self.answers['manual']:
            self._run_iterator(self._run_actions(self.answers['manual']))

    def guided(self, method):
        v = GuidedDiskSelectionView(self.model, self, method)
        self.ui.set_body(v)
        if self.answers['guided']:
            index = self.answers['guided-index']
            disk = self.model.all_disks()[index]
            v.choose_disk(None, disk.path)

    def reset(self):
        log.info("Resetting Filesystem model")
        self.model.reset()
        self.manual()

    def cancel(self):
        self.showing = False
        self.signal.emit_signal('prev-screen')

    def finish(self):
        self.showing = False
        log.debug("FilesystemController.finish next-screen")
        # start curtin install in background
        self.signal.emit_signal('installprogress:filesystem-config-done')
        # switch to next screen
        self.signal.emit_signal('next-screen')

    def create_mount(self, fs, spec):
        if spec.get('mount') is None:
            return
        mount = self.model.add_mount(fs, spec['mount'])
        return mount

    def delete_mount(self, mount):
        if mount is None:
            return
        self.model.remove_mount(mount)

    def create_filesystem(self, volume, spec):
        if spec['fstype'] is None or spec['fstype'].label is None:
            return
        fs = self.model.add_filesystem(volume, spec['fstype'].label)
        if isinstance(volume, Partition):
            if spec['fstype'].label == "swap":
                volume.flag = "swap"
            elif volume.flag == "swap":
                volume.flag = ""
        if spec['fstype'].label == "swap":
            self.model.add_mount(fs, "")
        self.create_mount(fs, spec)
        return fs

    def delete_filesystem(self, fs):
        if fs is None:
            return
        self.delete_mount(fs.mount())
        self.model.remove_filesystem(fs)

    def create_partition(self, device, spec, flag="", wipe=None):
        part = self.model.add_partition(device, spec["size"], flag, wipe)
        self.create_filesystem(part, spec)
        return part

    def delete_partition(self, part):
        self.delete_filesystem(part.fs())
        self.model.remove_partition(part)

    def _create_boot_partition(self, disk):
        if self.is_uefi():
            part_size = UEFI_GRUB_SIZE_BYTES
            if UEFI_GRUB_SIZE_BYTES*2 >= disk.size:
                part_size = disk.size // 2
            log.debug('Adding EFI partition first')
            part = self.create_partition(
                disk,
                dict(
                    size=part_size,
                    fstype=self.model.fs_by_name['fat32'],
                    mount='/boot/efi'),
                flag="boot")
        elif self.is_prep():
            log.debug('Adding PReP gpt partition first')
            part = self.create_partition(
                disk,
                dict(
                    size=PREP_GRUB_SIZE_BYTES,
                    fstype=None,
                    mount=None),
                # must be wiped or grub-install will fail
                wipe='zero',
                flag='prep')
        else:
            log.debug('Adding grub_bios gpt partition first')
            part = self.create_partition(
                disk,
                dict(
                    size=BIOS_GRUB_SIZE_BYTES,
                    fstype=None,
                    mount=None),
                flag='bios_grub')
        # should _not_ specify grub device for prep
        if not self.is_prep():
            disk.grub_device = True
        return part

    def create_raid(self, spec):
        for d in spec['devices']:
            self.delete_filesystem(d.fs())
        raid = self.model.add_raid(
            spec['name'],
            spec['level'].value,
            spec['devices'],
            spec['spare_devices'])
        return raid

    def delete_raid(self, raid):
        if raid is None:
            return
        self.delete_raid(raid.constructed_device())  # XXX
        self.delete_filesystem(raid.fs())
        for p in raid.partitions():
            self.delete_partition(p)
        self.model.remove_raid(raid)

    def create_volgroup(self, spec):
        devices = set()
        key = spec.get('password')
        for device in spec['devices']:
            self.delete_filesystem(device.fs())
            if key:
                device = self.model.add_dm_crypt(device, key)
            devices.add(device)
        return self.model.add_volgroup(name=spec['name'], devices=devices)
    create_lvm_volgroup = create_volgroup

    def delete_volgroup(self, vg):
        for lv in vg._partitions:
            self.delete_logical_volume(lv)
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
        self.delete_filesystem(lv.fs())
        self.model.remove_logical_volume(lv)
    delete_lvm_partition = delete_logical_volume

    def partition_disk_handler(self, disk, partition, spec):
        log.debug('partition_disk_handler: %s %s %s', disk, partition, spec)
        log.debug('disk.freespace: {}'.format(disk.free_for_partitions))

        if partition is not None:
            partition.size = align_up(spec['size'])
            if disk.free_for_partitions < 0:
                raise Exception("partition size too large")
            self.delete_filesystem(partition.fs())
            self.create_filesystem(partition, spec)
            return

        needs_boot = self.model.needs_bootloader_partition()
        log.debug('model needs a bootloader partition? {}'.format(needs_boot))
        can_be_boot = DeviceAction.MAKE_BOOT in disk.supported_actions
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

        log.info("Successfully added partition")

    def logical_volume_handler(self, vg, lv, spec):
        log.debug('logical_volume_handler: %s %s %s', vg, lv, spec)
        log.debug('vg.freespace: {}'.format(vg.free_for_partitions))

        if lv is not None:
            lv.name = spec['name']
            lv.size = align_up(spec['size'])
            if vg.free_for_partitions < 0:
                raise Exception("lv size too large")
            self.delete_filesystem(lv.fs())
            self.create_filesystem(lv, spec)
            return

        self.create_logical_volume(vg, spec)

    def add_format_handler(self, volume, spec):
        log.debug('add_format_handler %s %s', volume, spec)
        self.delete_filesystem(volume.fs())
        self.create_filesystem(volume, spec)

    def raid_handler(self, existing, spec):
        log.debug("raid_handler %s %s", existing, spec)
        if existing is not None:
            for d in existing.devices | existing.spare_devices:
                d._constructed_device = None
            for d in spec['devices'] | spec['spare_devices']:
                self.delete_filesystem(d.fs())
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
                self.delete_filesystem(d.fs())
                if key:
                    d = self.model.add_dm_crypt(d, key)
                d._constructed_device = existing
                devices.add(d)
            existing.name = spec['name']
            existing.devices = devices
        else:
            self.create_volgroup(spec)

    def make_boot_disk(self, new_boot_disk):
        boot_partition = None
        for disk in self.model.all_disks():
            for part in disk.partitions():
                if part.flag in ("bios_grub", "boot", "prep"):
                    boot_partition = part
        if boot_partition is not None:
            boot_disk = boot_partition.device
            full = boot_disk.free_for_partitions == 0
            self.delete_partition(boot_partition)
            boot_disk.grub_device = False
            if full:
                largest_part = max(
                    boot_disk.partitions(), key=lambda p: p.size)
                largest_part.size += boot_partition.size
            if new_boot_disk.free_for_partitions < boot_partition.size:
                largest_part = max(
                    new_boot_disk.partitions(), key=lambda p: p.size)
                largest_part.size -= (
                    boot_partition.size - new_boot_disk.free_for_partitions)
        self._create_boot_partition(new_boot_disk)

    def is_uefi(self):
        if self.opts.dry_run:
            return self.opts.uefi

        return os.path.exists('/sys/firmware/efi')

    def is_prep(self):
        return platform.machine().startswith("ppc64")
