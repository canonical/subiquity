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

from subiquity.controllers.policy import ControllerPolicy
from subiquity.views.filesystem import FilesystemView
from subiquity.models.filesystem import FilesystemModel, DiskPartitionModel
from subiquity.curtin import curtin_write_storage_actions

import logging
import subprocess


log = logging.getLogger('subiquity.filesystemController')


class DiskPartitionController(ControllerPolicy):
    """ Disk partition modification controller """
    def show(self, disk=None):
        self.ui.set_header("Partition, format and mount {}".format(disk))
        model = DiskPartitionModel()
        pass

    def finish(self, reset=False):
        pass


class FilesystemController(ControllerPolicy):
    """ Filesystem Controller """

    title = "Filesystem setup"

    footer = ("Select available disks to format and mount")

    def show(self, *args, **kwds):
        self.ui.set_header(self.title)
        self.ui.set_footer(self.footer)
        model = FilesystemModel()
        self.ui.set_body(FilesystemView(model, self.finish))
        return

    def finish(self, reset=False, actions=None):
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

__controller_class__ = FilesystemController
