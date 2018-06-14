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

import logging
import os

from subiquitycore.controller import BaseController

from subiquity.models.filesystem import (
    align_up,
    DeviceAction,
    Partition,
    )
from subiquity.ui.views import (
    FilesystemView,
    GuidedDiskSelectionView,
    GuidedFilesystemView,
    )


log = logging.getLogger("subiquitycore.controller.filesystem")

BIOS_GRUB_SIZE_BYTES = 1 * 1024 * 1024   # 1MiB
UEFI_GRUB_SIZE_BYTES = 512 * 1024 * 1024  # 512MiB EFI partition


class FilesystemController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.filesystem
        self.answers = self.all_answers.get("Filesystem", {})
        self.answers.setdefault('guided', False)
        self.answers.setdefault('guided-index', 0)
        self.answers.setdefault('manual', [])
        self.model.probe()  # probe before we complete

    def default(self):
        self.ui.set_body(GuidedFilesystemView(self))
        if self.answers['guided']:
            self.guided()
        elif self.answers['manual']:
            self.manual()

    def _action_get(self, id):
        if id.startswith('disk-index-'):
            index = id[len('disk-index-'):]
            if '-' in index:
                index, part_spec = index.split('-', 1)
                disk = self.model.all_disks()[int(index)]
                if part_spec.startswith('part-index-'):
                    part_index = part_spec[len('part-index-'):]
                    return disk.partitions()[int(part_index)]
            else:
                return self.model.all_disks()[int(index)]
        elif id.startswith('raid-'):
            name = id[len('raid-'):]
            for r in self.model.all_raids():
                if r.name == name:
                    return r
        raise Exception("could not resolve {}".format(id))

    def _action_clean_fstype(self, fstype):
        return self.model.fs_by_name[fstype]

    def _enter_form_data(self, data):
        form = self.ui.frame.body._w.stretchy.form
        for k, v in data.items():
            c = getattr(self, '_action_clean_{}'.format(k), lambda x: x)
            getattr(form, k).value = c(v)
            yield
        yield
        for bf in form._fields:
            bf.validate()
        form.validated()
        if not form.done_btn.enabled:
            raise Exception("answers left form invalid!")
        form._click_done(None)

    def _answers_action(self, action):
        from subiquitycore.ui.stretchy import StretchyOverlay
        if 'obj' in action:
            obj = self._action_get(action['obj'])
            meth = getattr(
                self.ui.frame.body.avail_list,
                "_{}_{}".format(obj.type, action['action']))
            meth(obj)
            yield
            if not isinstance(self.ui.frame.body._w, StretchyOverlay):
                return
            yield from self._enter_form_data(action['data'])
        elif action['action'] == 'done':
            if not self.ui.frame.body.done.enabled:
                raise Exception("answers did not provide complete fs config")
            self.finish()
        else:
            raise Exception("could not process action {}".format(action))

    def _run_actions(self, actions):
        for action in actions:
            yield from self._answers_action(action)

    def _run_iterator(self, it):
        try:
            next(it)
        except StopIteration:
            return
        self.loop.set_alarm_in(
            0.2,
            lambda *args: self._run_iterator(it))

    def manual(self):
        self.ui.set_body(FilesystemView(self.model, self))
        if self.answers['guided']:
            self.finish()
        if self.answers['manual']:
            self._run_iterator(self._run_actions(self.answers['manual']))

    def guided(self):
        v = GuidedDiskSelectionView(self.model, self)
        self.ui.set_body(v)
        if self.answers['guided']:
            index = self.answers['guided-index']
            disk = self.model.all_disks()[index]
            v.choose_disk(None, disk)

    def reset(self):
        log.info("Resetting Filesystem model")
        self.model.reset()
        self.manual()

    def cancel(self):
        self.signal.emit_signal('prev-screen')

    def finish(self):
        # start curtin install in background
        self.signal.emit_signal('installprogress:filesystem-config-done')
        # switch to next screen
        self.signal.emit_signal('next-screen')

    def create_mount(self, fs, spec):
        if spec['mount'] is None:
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

    def create_partition(self, device, spec, flag=""):
        part = self.model.add_partition(device, spec["size"], flag)
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
        else:
            log.debug('Adding grub_bios gpt partition first')
            part = self.create_partition(
                disk,
                dict(
                    size=BIOS_GRUB_SIZE_BYTES,
                    fstype=None,
                    mount=None),
                flag='bios_grub')
        disk.grub_device = True
        return part

    def partition_disk_handler(self, disk, partition, spec):
        log.debug('partition_disk_handler: %s %s %s', disk, partition, spec)
        log.debug('disk.freespace: {}'.format(disk.free))

        if partition is not None:
            partition.size = align_up(spec['size'])
            if disk.free < 0:
                raise Exception("partition size too large")
            self.delete_filesystem(partition.fs())
            self.create_filesystem(partition, spec)
            return

        bootable = self.model.bootable()
        log.debug('model has bootable device? {}'.format(bootable))
        can_be_boot = disk.supports_action(DeviceAction.MAKE_BOOT)
        if not bootable and len(disk.partitions()) == 0 and can_be_boot:
            part = self._create_boot_partition(disk)

            # adjust downward the partition size (if necessary) to accommodate
            # bios/grub partition
            if spec['size'] > disk.free:
                log.debug("Adjusting request down:" +
                          "{} - {} = {}".format(spec['size'], part.size,
                                                disk.free))
                spec['size'] = disk.free

        self.create_partition(disk, spec)

        log.info("Successfully added partition")

    def add_format_handler(self, volume, spec):
        log.debug('add_format_handler %s %s', volume, spec)
        self.delete_filesystem(volume.fs())
        self.create_filesystem(volume, spec)

    def make_boot_disk(self, disk):
        # XXX This violates abstractions, needs some thinking.
        for p in self.model._partitions:
            if p.flag in ("bios_grub", "boot"):
                full = p.device.free == 0
                p.device._partitions.remove(p)
                p.device.grub_device = False
                if full:
                    largest_part = max((part.size, part)
                                       for part in p.device._partitions)[1]
                    largest_part.size += p.size
                if disk.free < p.size:
                    largest_part = max((part.size, part)
                                       for part in disk._partitions)[1]
                    largest_part.size -= (p.size - disk.free)
                disk._partitions.insert(0, p)
                disk.grub_device = True
                p.device = disk
                return
        self._create_boot_partition(disk)

    def is_uefi(self):
        if self.opts.dry_run:
            return self.opts.uefi

        return os.path.exists('/sys/firmware/efi')
