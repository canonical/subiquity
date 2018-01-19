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
import re

from subiquitycore.controller import BaseController
from subiquitycore.ui.dummy import DummyView
from subiquitycore.ui.error import ErrorView

from subiquity.models.filesystem import humanize_size, dehumanize_size
from subiquity.ui.views import (
    BcacheView,
    DiskInfoView,
    DiskPartitionView,
    FilesystemView,
    FormatEntireView,
    GuidedDiskSelectionView,
    GuidedFilesystemView,
    LVMVolumeGroupView,
    PartitionView,
    RaidView,
    )


log = logging.getLogger("subiquitycore.controller.filesystem")

BIOS_GRUB_SIZE_BYTES = 2 * 1024 * 1024   # 2MiB
UEFI_GRUB_SIZE_BYTES = 512 * 1024 * 1024  # 512MiB EFI partition


class FilesystemController(BaseController):

    def __init__(self, common):
        super().__init__(common)
        self.model = self.base_model.filesystem
        self.answers = self.all_answers.get("Filesystem", {})
        self.answers.setdefault('guided', False)
        self.answers.setdefault('guided-index', 0)
        self.answers.setdefault('manual', False)
        self.answers.setdefault('volumes', None)
        # self.iscsi_model = IscsiDiskModel()
        # self.ceph_model = CephDiskModel()
        self.model.probe()  # probe before we complete

    def default(self):
        title = _("Filesystem setup")
        footer = (_("Choose guided or manual partitioning"))
        self.ui.set_header(title)
        self.ui.set_footer(footer)
        self.ui.set_body(GuidedFilesystemView(self))
        if self.answers['guided']:
            self.guided()
        elif self.answers['volumes']:
            self.part_answers()
        elif self.answers['manual']:
            self.manual()

    def _validate_volumes_input(self, disk, size, flag, fstype, fslabel, mount):
        if size is not None and size > disk.free:
            log.debug('Partition size({}) greater than free size({})'.format(size, disk.free))
            return False
        if flag is not None and flag != 'boot' and flag != 'bios_grub':
            log.debug('Not supported flag:{}'.format(flag))
            return False
        if fslabel is not None:
            if fstype == 'ext4' and len(fslabel) > 16:
                return False
            elif fstype == 'fat32' and len(fslabel) > 11:
                return False
            elif fstype == 'btrfs' and len(fslabel) > 256:
                return False
            elif fstype == 'swap' and len(fslabel) > 15:
                return False
            elif fstype == 'xfs' and len(fslabel) > 12:
                return False
        if fstype is None and mount is not None:
            log.debug('Mounted partition({}) but without filesystem'.format(mount))
            return False
        elif fstype == 'swap' and mount is not None:
            log.debug('swap partition is not allow to be mounted')
            return False
        if mount is None:
            return True
        else:
            r = re.compile('^(/)+[a-zA-Z0-9_/\.\-]?')
            if r.match(mount) is None:
                log.debug('Invalid mount path:{}'.format(mount))
                return False
            # /usr/include/linux/limits.h:PATH_MAX
            if len(mount) > 4095:
                log.debug('Path exceeds PATH_MAX')
                return False
            mountpoint_to_devpath_mapping = self.model.get_mountpoint_to_devpath_mapping()
            dev = mountpoint_to_devpath_mapping.get(mount)
            if dev is not None:
                log.debug('{} is already mounted at {}'.format(dev, mount))
                return False
        return True

    def _force_manual(self, reason):
        log.debug('Force manual, {}'.format(reason))
        self.answers['volumes'] = False
        self.reset()

    def part_answers(self):
        log.debug("Partitions configure in answers")
        for disks in self.answers['volumes']:
            for d, parts in disks.items():
                disk = None
                r_disk = re.compile('disk-[0-9]$')
                # case 1: /dev/sdX
                # case 2: /dev/nvmeXnX
                # case 3: /dev/dm-X
                r_devpath = re.compile('^(/dev/)+([a-z])+([0-9n-])*')
                if r_disk.match(d) is not None:
                    index = d.strip('disk-')
                    disk = self.model.all_disks()[int(index)]
                elif r_devpath.match(d) is not None:
                    disk = self.model.get_disk(d)
                if disk is None:
                    self._force_manual(reason='Unknown volume: {}'.format(d))
                    return
                partnum = 0
                for p in parts:
                    # if size leaves as empty, using remain space as partition size
                    if 'size' not in p or None is p['size']:
                        size = dehumanize_size(str(disk.free))
                    else:
                        size = dehumanize_size(str(p['size']))
                    if 'flag' in p:
                        flag = p['flag']
                    else:
                        flag = None
                    try:
                        fstype = self.model.fs_by_name[p['filesystem']]
                    except KeyError:
                        fstype = None
                    if 'mount' in p:
                        mount = p['mount']
                    else:
                        mount = None
                    if 'filesystem-label' in p:
                        fslabel = p['filesystem-label']
                    else:
                        fslabel = None
                    if not self._validate_volumes_input(disk, size, flag, fstype, fslabel, mount):
                        self._force_manual(reason=
                                'Invalid partition attributes: size:{}, flag:{}, fstype: {}, fslabel: {}, mount:{}'
                                .format(size, flag, fstype, fslabel, mount))
                        return
                    partnum += 1
                    part = self.model.add_partition(disk=disk, partnum=partnum, size=size, flag=flag)
                    spec = {
                        "partnum": partnum,
                        "size": size,
                        "fstype": fstype,
                        "fslabel": fslabel,
                        "mount": mount,
                    }
                    self.partition_disk_handler(disk, part, spec)
        if not self.model.can_install():
            self._force_manual(reason='The partitions not installable:{}'.format(self.model._partitions))
            return
        self.manual()

    def manual(self):
        title = _("Filesystem setup")
        footer = (_("Select available disks to format and mount"))
        self.ui.set_header(title)
        self.ui.set_footer(footer)
        self.ui.set_body(FilesystemView(self.model, self))
        if self.answers['guided'] or self.answers['volumes']:
            self.finish()

    def guided(self):
        title = _("Filesystem setup")
        footer = (_("Choose the installation target"))
        self.ui.set_header(title)
        self.ui.set_footer(footer)
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

    def filesystem_error(self, error_fname):
        title = _("Filesystem error")
        footer = (_("Error while installing Ubuntu"))
        error_msg = _("Failed to obtain write permissions to /tmp")
        self.ui.set_header(title)
        self.ui.set_footer(footer)
        self.ui.set_body(ErrorView(self.signal, error_msg))

    def finish(self):
        # start curtin install in background
        self.signal.emit_signal('installprogress:filesystem-config-done')
        # switch to next screen
        self.signal.emit_signal('next-screen')

    # Filesystem/Disk partition -----------------------------------------------
    def partition_disk(self, disk):
        log.debug("In disk partition view, using {} as the disk.".format(disk.serial))
        title = (_("Partition, format, and mount {}").format(disk.serial))
        footer = (_("Partition the disk, or format the entire device "
                  "without partitions"))
        self.ui.set_header(title)
        self.ui.set_footer(footer)
        dp_view = DiskPartitionView(self.model, self, disk)

        self.ui.set_body(dp_view)

    def add_disk_partition(self, disk):
        log.debug("Adding partition to {}".format(disk))
        footer = _("Select whole disk, or partition, to format and mount.")
        self.ui.set_footer(footer)
        adp_view = PartitionView(self.model, self, disk)
        self.ui.set_body(adp_view)

    def edit_partition(self, disk, partition):
        log.debug("Editing partition {}".format(partition))
        footer = _("Edit partition details format and mount.")
        self.ui.set_footer(footer)
        adp_view = PartitionView(self.model, self, disk, partition)
        self.ui.set_body(adp_view)

    def delete_partition(self, part):
        old_fs = part.fs()
        if old_fs is not None:
            self.model._filesystems.remove(old_fs)
            part._fs = None
            mount = old_fs.mount()
            if mount is not None:
                old_fs._mount = None
                self.model._mounts.remove(mount)
        part.device.partitions().remove(part)
        self.model._partitions.remove(part)
        self.partition_disk(part.device)

    def partition_disk_handler(self, disk, partition, spec):
        log.debug('spec: {}'.format(spec))
        log.debug('disk.freespace: {}'.format(disk.free))

        if partition is not None:
            partition.number = spec['partnum']
            partition.size = spec['size']
            old_fs = partition.fs()
            if old_fs is not None:
                self.model._filesystems.remove(old_fs)
                partition._fs = None
                mount = old_fs.mount()
                if mount is not None:
                    old_fs._mount = None
                    self.model._mounts.remove(mount)
            if spec['fstype'].label is not None:
                if 'fslabel' in spec:
                    fslabel = spec['fslabel']
                else:
                    fslabel = ""
                fs = self.model.add_filesystem(partition, spec['fstype'].label, fslabel=fslabel)
                if spec['mount']:
                  self.model.add_mount(fs, spec['mount'])
            self.partition_disk(disk)
            return

        system_bootable = self.model.bootable()
        log.debug('model has bootable device? {}'.format(system_bootable))
        if not system_bootable and len(disk.partitions()) == 0:
            if self.is_uefi():
                log.debug('Adding EFI partition first')
                part = self.model.add_partition(disk=disk, partnum=1, size=UEFI_GRUB_SIZE_BYTES, flag='boot')
                fs = self.model.add_filesystem(part, 'fat32')
                self.model.add_mount(fs, '/boot/efi')
            else:
                log.debug('Adding grub_bios gpt partition first')
                part = self.model.add_partition(disk=disk, partnum=1, size=BIOS_GRUB_SIZE_BYTES, flag='bios_grub')
            disk.grub_device = True

            # adjust downward the partition size to accommodate
            # the offset and bios/grub partition
            # XXX should probably only do this if the partition is now too big to fit on the disk?
            log.debug("Adjusting request down:" +
                      "{} - {} = {}".format(spec['size'], part.size,
                                            spec['size'] - part.size))
            spec['size'] -= part.size
            spec['partnum'] = 2

        part = self.model.add_partition(disk=disk, partnum=spec["partnum"], size=spec["size"])
        if spec['fstype'].label is not None:
            fs = self.model.add_filesystem(part, spec['fstype'].label)
            if spec['mount']:
                self.model.add_mount(fs, spec['mount'])

        log.info("Successfully added partition")
        self.partition_disk(disk)

    def add_format_handler(self, volume, spec, back):
        log.debug('add_format_handler')
        old_fs = volume.fs()
        if old_fs is not None:
            self.model._filesystems.remove(old_fs)
            volume._fs = None
            mount = old_fs.mount()
            if mount is not None:
                old_fs._mount = None
                self.model._mounts.remove(mount)
        if spec['fstype'].label is not None:
            fs = self.model.add_filesystem(volume, spec['fstype'].label)
            if spec['mount']:
                self.model.add_mount(fs, spec['mount'])
        back()

    def connect_iscsi_disk(self, *args, **kwargs):
        # title = ("Disk and filesystem setup")
        # excerpt = ("Connect to iSCSI cluster")
        # self.ui.set_header(title, excerpt)
        # self.ui.set_footer("")
        # self.ui.set_body(IscsiDiskView(self.iscsi_model,
        #                                self.signal))
        self.ui.set_body(DummyView(self.signal))

    def connect_ceph_disk(self, *args, **kwargs):
        # title = ("Disk and filesystem setup")
        # footer = ("Select available disks to format and mount")
        # excerpt = ("Connect to Ceph storage cluster")
        # self.ui.set_header(title, excerpt)
        # self.ui.set_footer(footer)
        # self.ui.set_body(CephDiskView(self.ceph_model,
        #                               self.signal))
        self.ui.set_body(DummyView(self.signal))

    def create_volume_group(self, *args, **kwargs):
        title = ("Create Logical Volume Group (\"LVM2\") disk")
        footer = ("ENTER on a disk will show detailed "
                  "information for that disk")
        excerpt = ("Use SPACE to select disks to form your LVM2 volume group, "
                   "and then specify the Volume Group name. ")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(LVMVolumeGroupView(self.model, self.signal))

    def create_raid(self, *args, **kwargs):
        title = ("Create software RAID (\"MD\") disk")
        footer = ("ENTER on a disk will show detailed "
                  "information for that disk")
        excerpt = ("Use SPACE to select disks to form your RAID array, "
                   "and then specify the RAID parameters. Multiple-disk "
                   "arrays work best when all the disks in an array are "
                   "the same size and speed.")
        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(RaidView(self.model,
                                  self.signal))

    def create_bcache(self, *args, **kwargs):
        title = ("Create hierarchical storage (\"bcache\") disk")
        footer = ("ENTER on a disk will show detailed "
                  "information for that disk")
        excerpt = ("Use SPACE to select a cache disk and a backing disk"
                   " to form your bcache device.")

        self.ui.set_header(title, excerpt)
        self.ui.set_footer(footer)
        self.ui.set_body(BcacheView(self.model,
                                    self.signal))

    def add_raid_dev(self, result):
        log.debug('add_raid_dev: result={}'.format(result))
        self.model.add_raid_device(result)
        self.signal.prev_signal()

    def format_entire(self, disk):
        log.debug("format_entire {}".format(disk.serial))
        header = (_("Format and/or mount {}").format(disk.serial))
        footer = _("Format or mount whole disk.")
        self.ui.set_header(header)
        self.ui.set_footer(footer)
        afv_view = FormatEntireView(self.model, self, disk, lambda : self.partition_disk(disk))
        self.ui.set_body(afv_view)

    def format_mount_partition(self, partition):
        log.debug("format_entire {}".format(partition))
        if partition.fs() is not None:
            header = (_("Mount partition {} of {}").format(partition.number, partition.device.serial))
            footer = _("Mount partition.")
        else:
            header = (_("Format and mount partition {} of {}").format(partition.number, partition.device.serial))
            footer = _("Format and mount partition.")
        self.ui.set_header(header)
        self.ui.set_footer(footer)
        afv_view = FormatEntireView(self.model, self, partition, self.manual)
        self.ui.set_body(afv_view)

    def show_disk_information_next(self, disk):
        log.debug('show_disk_info_next: curr_device={}'.format(disk))
        available = self.model.all_disks()
        idx = available.index(disk)
        next_idx = (idx + 1) % len(available)
        next_device = available[next_idx]
        self.show_disk_information(next_device)

    def show_disk_information_prev(self, disk):
        log.debug('show_disk_info_prev: curr_device={}'.format(disk))
        available = self.model.all_disks()
        idx = available.index(disk)
        next_idx = (idx - 1) % len(available)
        next_device = available[next_idx]
        self.show_disk_information(next_device)

    def show_disk_information(self, disk):
        """ Show disk information, requires sudo/root
        """
        bus = disk._info.raw.get('ID_BUS', None)
        major = disk._info.raw.get('MAJOR', None)
        if bus is None and major == '253':
            bus = 'virtio'

        devpath = disk._info.raw.get('DEVPATH', disk.path)
        rotational = '1'
        try:
            dev = os.path.basename(devpath)
            rfile = '/sys/class/block/{}/queue/rotational'.format(dev)
            rotational = open(rfile, 'r').read().strip()
        except (PermissionError, FileNotFoundError, IOError):
            log.exception('WARNING: Failed to read file {}'.format(rfile))
            pass

        dinfo = {
            'bus': bus,
            'devname': disk.path,
            'devpath': devpath,
            'model': disk.model,
            'serial': disk.serial,
            'size': disk.size,
            'humansize': humanize_size(disk.size),
            'vendor': disk._info.vendor,
            'rotational': 'true' if rotational == '1' else 'false',
        }

        template = """\n
{devname}:\n
 Vendor: {vendor}
 Model: {model}
 SerialNo: {serial}
 Size: {humansize} ({size}B)
 Bus: {bus}
 Rotational: {rotational}
 Path: {devpath}
"""
        result = template.format(**dinfo)
        log.debug('calling DiskInfoView()')
        disk_info_view = DiskInfoView(self.model, self, disk, result)
        footer = _('Select next or previous disks with n and p')
        self.ui.set_footer(footer)
        self.ui.set_body(disk_info_view)

    def is_uefi(self):
        if self.opts.dry_run and self.opts.uefi:
            log.debug('forcing is_uefi True beacuse of options')
            return True

        return os.path.exists('/sys/firmware/efi')
