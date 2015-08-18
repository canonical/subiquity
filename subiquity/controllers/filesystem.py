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
import urwid
from subiquity.controller import ControllerPolicy
from subiquity.models import FilesystemModel
from subiquity.ui.views import (DiskPartitionView, AddPartitionView,
                                FilesystemView)
from subiquity.ui.dummy import DummyView
from subiquity.curtin import (curtin_write_storage_actions,
                              curtin_write_postinst_config)


log = logging.getLogger("subiquity.controller.filesystem")

BIOS_GRUB_SIZE_BYTES = 2 * 1024 * 1024   # 2MiB


class FilesystemController(ControllerPolicy):
    def __init__(self, ui, signal):
        self.ui = ui
        self.signal = signal
        self.model = FilesystemModel()

    def filesystem(self, reset=False):
        # FIXME: Is this the best way to zero out this list for a reset?
        if reset:
            log.info("Resetting Filesystem model")
            self.model.reset()

        title = "Filesystem setup"
        footer = ("Select available disks to format and mount")
        self.ui.set_header(title)
        self.ui.set_footer(footer)
        self.ui.set_body(FilesystemView(self.model,
                                        self.signal))

    def filesystem_handler(self, reset=False, actions=None):
        if actions is None and reset is False:
            urwid.emit_signal(self.signal, 'network:show')

        log.info("Rendering curtin config from user choices")
        curtin_write_storage_actions(actions=actions)
        log.info("Generating post-install config")
        curtin_write_postinst_config()
        urwid.emit_signal(self.signal, 'identity:show')
        # self.install_progress()

    # Filesystem/Disk partition -----------------------------------------------
    def disk_partition(self, disk):
        log.debug("In disk partition view, using {} as the disk.".format(disk))
        title = ("Partition, format, and mount {}".format(disk))
        footer = ("Partition the disk, or format the entire device "
                  "without partitions.")
        self.ui.set_header(title)
        self.ui.set_footer(footer)
        dp_view = DiskPartitionView(self.model,
                                    self.signal,
                                    disk)

        self.ui.set_body(dp_view)

    def disk_partition_handler(self, spec=None):
        log.debug("Disk partition: {}".format(spec))
        if spec is None:
            urwid.emit_signal(self.signal, 'filesystem:show', [])
        urwid.emit_signal(self.signal, 'filesystem:show-disk-partition', [])

    def add_disk_partition(self, disk):
        log.debug("Adding partition to {}".format(disk))
        footer = ("Select whole disk, or partition, to format and mount.")
        self.ui.set_footer(footer)
        adp_view = AddPartitionView(self.model,
                                    self.signal,
                                    disk)
        self.ui.set_body(adp_view)

    def add_disk_partition_handler(self, disk, spec):
        current_disk = self.model.get_disk(disk)

        ''' create a gpt boot partition if one doesn't exist '''
        if current_disk.parttype == 'gpt' and \
           len(current_disk.disk.partitions) == 0:
            log.debug('Adding grub_bios gpt partition first')
            current_disk.add_partition(partnum=1,
                                       size=BIOS_GRUB_SIZE_BYTES,
                                       fstype=None,
                                       flag='bios_grub')

        if spec["fstype"] in ["swap"]:
            current_disk.add_partition(partnum=spec["partnum"],
                                       size=spec["bytes"],
                                       fstype=spec["fstype"])
        else:
            current_disk.add_partition(partnum=spec["partnum"],
                                       size=spec["bytes"],
                                       fstype=spec["fstype"],
                                       mountpoint=spec["mountpoint"])
        log.debug("FS Table: {}".format(current_disk.get_fs_table()))
        self.signal.emit_signal('filesystem:show-disk-partition', disk)

    def connect_iscsi_disk(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def connect_ceph_disk(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def create_volume_group(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def create_raid(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def setup_bcache(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def add_first_gpt_partition(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))

    def create_swap_entire_device(self, *args, **kwargs):
        self.ui.set_body(DummyView(self.signal))
