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

from subiquity.views.filesystem import (FilesystemView,
                                        DiskPartitionView)
from subiquity.models.filesystem import FilesystemModel
from subiquity.curtin import curtin_write_storage_actions

from urwid import connect_signal
import logging
import subprocess


log = logging.getLogger('subiquity.filesystemController')


class FilesystemController:
    """ Filesystem Controller """
    fs_model = FilesystemModel()

    def __init__(self, ui):
        self.ui = ui

    # Filesystem actions
    def show(self, *args, **kwds):
        title = "Filesystem setup"
        footer = ("Select available disks to format and mount")

        fs_view = FilesystemView(self.fs_model)
        connect_signal(fs_view, 'fs:done', self.finish)
        connect_signal(fs_view, 'fs:dp:view', self.show_disk_partition_view)

        self.ui.set_header(title)
        self.ui.set_footer(footer)
        self.ui.set_body(fs_view)
        return

    def finish(self, reset=False, actions=None):
        """
        :param bool reset: Reset model options
        :param actions: storage actions

        Signal:
        key: 'fs:done'
        usage: emit_signal(self, 'fs:done', (reset, actions))
        """
        if actions is None and reset is False:
            return self.ui.prev_controller()

        log.info("Rendering curtin config from user choices")
        curtin_write_storage_actions(actions=actions)
        if self.ui.opts.dry_run:
            log.debug("filesystem: this is a dry-run")
            print("\033c")
            print("**** DRY_RUN ****")
            print('NOT calling: '
                  'subprocess.check_call("/usr/local/bin/curtin_wrap.sh")')
            print("**** DRY_RUN ****")
        else:
            log.debug("filesystem: this is the *real* thing")
            print("\033c")
            print("**** Calling curtin installer ****")
            subprocess.check_call("/usr/local/bin/curtin_wrap.sh")

        return self.ui.exit()

    # DISK Partitioning actions
    def show_disk_partition_view(self, disk):
        log.debug("In disk partition view, using {} as the disk.".format(disk))
        title = ("Paritition, format, and mount {}".format(disk))
        footer = ("Paritition the disk, or format the entire device "
                  "without partitions.")
        self.ui.set_header(title)
        self.ui.set_footer(footer)
        dp_view = DiskPartitionView(self.fs_model,
                                    disk,
                                    self.finish_disk_paritition_view)

        connect_signal(dp_view, 'fs:dp:done', self.finish_disk_paritition_view)
        self.ui.set_body(dp_view)
        return

    def finish_disk_paritition_view(self, is_finish):
        log.debug("Finish disk-p-v: {}".format(is_finish))
        return self.ui.exit()


__controller_class__ = FilesystemController
