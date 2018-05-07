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

import attr

from urwid import (
    connect_signal,
    Text,
    )

from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.form import (
    ChoiceField,
    Form,
    StringField,
    )
from subiquitycore.ui.selector import (
    Option,
    )
from subiquitycore.ui.stretchy import (
    Stretchy,
    )

from .filesystem.partition import FSTypeField
from ..mount import MountField
from subiquity.models.filesystem import (
    get_raid_size,
    humanize_size,
    )

log = logging.getLogger('subiquity.ui.raid')

@attr.s
class RaidLevel:
    name = attr.ib()
    value = attr.ib()
    min_devices = attr.ib()


levels = [
    RaidLevel(_("0 (striped)"), 0, 2),
    RaidLevel(_("1 (mirrored)"), 1, 2),
    RaidLevel(_("5"), 5, 3),
    RaidLevel(_("6"), 6, 4),
    RaidLevel(_("10"), 10, 72),
    ]


class RaidForm(Form):

    def __init__(self, mountpoint_to_devpath_mapping, initial={}):
        self.mountpoint_to_devpath_mapping = mountpoint_to_devpath_mapping
        super().__init__(initial)
        connect_signal(self.fstype.widget, 'select', self.select_fstype)
        self.select_fstype(None, self.fstype.widget.value)

    name = StringField(_("Name:"))
    level = ChoiceField(_("RAID Level:"), choices=["dummy"])
    size = StringField(_("Size:"))

    def select_fstype(self, sender, fs):
        self.mount.enabled = fs.is_mounted

    fstype = FSTypeField(_("Format:"))
    mount = MountField(_("Mount:"))

    def clean_mount(self, val):
        if self.fstype.value.is_mounted:
            return val
        else:
            return None

    def validate_mount(self):
        mount = self.mount.value
        if mount is None:
            return
        # /usr/include/linux/limits.h:PATH_MAX
        if len(mount) > 4095:
            return _('Path exceeds PATH_MAX')
        dev = self.mountpoint_to_devpath_mapping.get(mount)
        if dev is not None:
            return _("%s is already mounted at %s")%(dev, mount)


class RaidStretchy(Stretchy):
    def __init__(self, parent, devices):
        self.parent = parent
        self.devices = devices

        self.form = RaidForm(self.parent.model.get_mountpoint_to_devpath_mapping(), {'name': 'dm-0'})

        connect_signal(self.form.level.widget, 'select', self._select_level)
        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        opts = []
        for level in levels:
            enabled = len(devices) >= level.min_devices
            opts.append(Option((_(level.name), enabled, level)))
        self.form.level.widget._options = opts
        self.form.level.widget.index = 0

        self.form.size.enabled = False

        title = _('Create software RAID ("MD") disk')
        super().__init__(title, [Pile(self.form.as_rows()), Text(""), self.form.buttons], 0, 0)

    def _select_level(self, sender, new_level):
        self.form.size.value = humanize_size(get_raid_size(new_level.value, self.devices))

    def done(self, sender):
        result = self.form.as_data()
        result['devices'] = self.devices
        log.debug('raid_done: result = {}'.format(result))
        self.parent.controller.add_raid(result)

    def cancel(self, sender):
        self.parent.remove_overlay()
