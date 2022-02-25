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
import re

from urwid import (
    connect_signal,
    Text,
    )

from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.form import (
    ChoiceField,
    ReadOnlyField,
    simple_field,
    WantsToKnowFormField,
    )
from subiquitycore.ui.interactive import (
    StringEditor,
    )
from subiquitycore.ui.selector import (
    Option,
    )
from subiquitycore.ui.stretchy import (
    Stretchy,
    )

from subiquity.models.filesystem import (
    get_raid_size,
    humanize_size,
    raidlevels,
    raidlevels_by_value,
    )
from subiquity.ui.views.filesystem.compound import (
    CompoundDiskForm,
    get_possible_components,
    MultiDeviceField,
    )

log = logging.getLogger('subiquity.ui.views.filesystem.raid')


raidlevel_choices = [
    Option((_(level.name), True, level))
    for level in raidlevels
    if level.value != "container"
]


class RaidnameEditor(StringEditor, WantsToKnowFormField):
    def valid_char(self, ch):
        if len(ch) == 1 and ch == '/':
            self.bff.in_error = True
            self.bff.show_extra(("info_error",
                                 _("/ is not permitted "
                                   "in the name of a RAID device")))
            return False
        elif len(ch) == 1 and ch.isspace():
            self.bff.in_error = True
            self.bff.show_extra(("info_error",
                                 _("Whitespace is not permitted in the "
                                   "name of a RAID device")))
            return False
        else:
            return super().valid_char(ch)


RaidnameField = simple_field(RaidnameEditor)


class RaidForm(CompoundDiskForm):

    def __init__(self, model, possible_components, initial, raid_names):
        self.raid_names = raid_names
        super().__init__(model, possible_components, initial)
        self.size.enabled = False

    name = RaidnameField(_("Name:"))
    level = ChoiceField(_("RAID Level:"), choices=raidlevel_choices)
    devices = MultiDeviceField(_("Devices:"))
    size = ReadOnlyField(_("Size:"))

    def clean_name(self, val):
        if not val:
            raise ValueError("The name cannot be empty")
        if not re.match('md[0-9]+', val):
            val = 'md/' + val
        return val

    def validate_name(self):
        if self.name.value in self.raid_names:
            return _("There is already a RAID named '{name}'").format(
                name=self.name.value)
        if self.name.value in ('/dev/md/.', '/dev/md/..'):
            return _(". and .. are not valid names for RAID devices")

    def validate_devices(self):
        active_device_count = len(self.devices.widget.active_devices)
        if active_device_count < self.level.value.min_devices:
            return _(
                'RAID Level "{level}" requires at least {min_active} active'
                ' devices').format(
                    level=self.level.value.name,
                    min_active=self.level.value.min_devices)
        return super().validate_devices()


class RaidStretchy(Stretchy):
    def __init__(self, parent, existing=None):
        self.parent = parent
        self.existing = existing
        raid_names = {raid.name for raid in parent.model.all_raids()}
        if existing is None:
            title = _('Create software RAID ("MD") disk')
            label = _('Create')
            x = 0
            while True:
                name = 'md{}'.format(x)
                if name not in raid_names:
                    break
                x += 1
            initial = {
                'devices': {},
                'name': name,
                'level': raidlevels_by_value["raid1"],
                'size': '-',
                }
        else:
            raid_names.remove(existing.name)
            title = _('Edit software RAID disk "{name}"').format(
                name=existing.name)
            label = _('Save')
            name = existing.name
            if name.startswith('md/'):
                name = name[3:]
            devices = {}
            for d in existing.devices:
                devices[d] = 'active'
            for d in existing.spare_devices:
                devices[d] = 'spare'
            initial = {
                'devices': devices,
                'name': name,
                'level': raidlevels_by_value[existing.raidlevel]
                }

        possible_components = get_possible_components(
            self.parent.model, existing, initial['devices'],
            lambda dev: dev.ok_for_raid)

        form = self.form = RaidForm(
            self.parent.model, possible_components, initial, raid_names)

        form.devices.widget.set_supports_spares(
            initial['level'].supports_spares)
        form.buttons.base_widget[0].set_label(label)

        connect_signal(form.level.widget, 'select', self._select_level)
        connect_signal(form.devices.widget, 'change', self._change_devices)
        connect_signal(form, 'submit', self.done)
        connect_signal(form, 'cancel', self.cancel)

        rows = form.as_rows()

        super().__init__(
            title,
            [Pile(rows), Text(""), self.form.buttons],
            0, 0)

    def _select_level(self, sender, new_level):
        active_device_count = len(self.form.devices.widget.active_devices)
        if active_device_count >= new_level.min_devices:
            self.form.size.value = humanize_size(
                get_raid_size(new_level.value, self.form.devices.value))
        else:
            self.form.size.value = '-'
        self.form.devices.widget.set_supports_spares(new_level.supports_spares)
        self.form.level.value = new_level
        self.form.devices.showing_extra = False
        self.form.devices.validate()

    def _change_devices(self, sender, new_devices):
        if len(sender.active_devices) >= self.form.level.value.min_devices:
            self.form.size.value = humanize_size(
                get_raid_size(self.form.level.value.value, new_devices))
        else:
            self.form.size.value = '-'

    def done(self, sender):
        result = self.form.as_data()
        mdc = self.form.devices.widget
        result['devices'] = mdc.active_devices
        result['spare_devices'] = mdc.spare_devices
        log.debug('raid_done: result = {}'.format(result))
        self.parent.controller.raid_handler(self.existing, result)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender):
        self.parent.remove_overlay()
