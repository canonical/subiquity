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
    CheckBox,
    connect_signal,
    Padding as UrwidPadding,
    Text,
    )

from subiquitycore.ui.container import (
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.form import (
    ChoiceField,
    Form,
    ReadOnlyField,
    simple_field,
    StringField,
    Toggleable,
    WantsToKnowFormField,
    )
from subiquitycore.ui.selector import (
    Option,
    Selector,
    )
from subiquitycore.ui.stretchy import (
    Stretchy,
    )
from subiquitycore.ui.table import (
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    Color,
    )

from subiquity.models.filesystem import (
    get_raid_size,
    humanize_size,
    raidlevels,
    raidlevels_by_value,
    )

log = logging.getLogger('subiquity.ui.raid')


LABEL, DEVICE, PART = range(3)


class MultiDeviceChooser(WidgetWrap, WantsToKnowFormField):
    signals = ['change']

    def __init__(self):
        self.table = TablePile([], spacing=1)
        self.device_to_checkbox = {}
        self.device_to_selector = {}
        self.devices = {}  # {device:active|spare}
        self.all_rows = []
        self.no_selector_rows = []
        self.supports_spares = True
        super().__init__(self.table)

    @property
    def value(self):
        return self.devices

    @value.setter
    def value(self, value):
        log.debug("MDC set value %s", {d.id: v for d, v in value.items()})
        self.devices = value
        for d, s in self.device_to_selector.items():
            if d in self.devices:
                s.enabled = True
                s.base_widget.value = self.devices[d]
            else:
                s.enabled = False
        for d, b in self.device_to_checkbox.items():
            b.set_state(d in self.devices)

    @property
    def active_devices(self):
        return {device for device, status in self.devices.items()
                if status == 'active'}

    @property
    def spare_devices(self):
        return {device for device, status in self.devices.items()
                if status == 'spare'}

    def set_supports_spares(self, val):
        if val == self.supports_spares:
            return
        self.supports_spares = val
        if val:
            for device in list(self.devices):
                selector = self.device_to_selector[device]
                selector.enabled = True
                self.devices[device] = selector.base_widget.value
            self.table.set_contents(self.all_rows)
        else:
            for device in list(self.devices):
                self.device_to_selector[device].enabled = False
                self.devices[device] = 'active'
            self.table.set_contents(self.no_selector_rows)

    def _state_change_device(self, sender, state, device):
        if state:
            if self.supports_spares:
                self.device_to_selector[device].enabled = True
            selector = self.device_to_selector[device]
            self.devices[device] = selector.base_widget.value
        else:
            self.device_to_selector[device].enabled = False
            del self.devices[device]
        self._emit('change', self.devices)

    def _select_active_spare(self, sender, value, device):
        self.devices[device] = value
        self._emit('change', self.devices)

    def _summarize(self, prefix, device):
        if device.fs() is not None:
            fs = device.fs()
            text = prefix + _("formatted as {}").format(fs.fstype)
            if fs.mount():
                text += _(", mounted at {}").format(fs.mount().path)
            else:
                text += _(", not mounted")
        else:
            text = prefix + _("unused {}").format(device.desc())
        return TableRow([(2, Color.info_minor(Text(text)))])

    def set_bound_form_field(self, bff):
        super().set_bound_form_field(bff)
        self.all_rows = []
        for kind, device in bff.form.all_devices:
            if kind == LABEL:
                self.all_rows.append(TableRow([
                    Text("    " + device.label),
                    Text(humanize_size(device.size), align='right')
                ]))
                self.no_selector_rows.append(self.all_rows[-1])
                self.all_rows.append(TableRow([
                    (2, Color.info_minor(Text("      " + device.desc())))
                ]))
                self.no_selector_rows.append(self.all_rows[-1])
            else:
                if kind == DEVICE:
                    label = device.label
                    prefix = "    "
                elif kind == PART:
                    label = _("  partition {}").format(device._number)
                    prefix = "      "
                else:
                    raise Exception("unexpected kind {}".format(kind))
                box = CheckBox(
                    label,
                    on_state_change=self._state_change_device,
                    user_data=device)
                self.device_to_checkbox[device] = box
                size = Text(humanize_size(device.size), align='right')
                self.all_rows.append(Color.menu_button(TableRow([box, size])))
                self.no_selector_rows.append(self.all_rows[-1])
                selector = Selector(['active', 'spare'])
                connect_signal(
                    selector, 'select', self._select_active_spare, device)
                selector = Toggleable(
                    UrwidPadding(
                        Color.menu_button(selector),
                        left=len(prefix)))
                selector.enabled = False
                self.device_to_selector[device] = selector
                self.all_rows.append(TableRow([(2, selector)]))
                # Do not append that one to no_selector_rows!
                self.all_rows.append(self._summarize(prefix, device))
                self.no_selector_rows.append(self.all_rows[-1])
        self.table.set_contents(self.all_rows)
        log.debug("%s", self.table._w.focus_position)


MultiDeviceField = simple_field(MultiDeviceChooser)
MultiDeviceField.takes_default_style = False


raidlevel_choices = [
    Option((_(level.name), True, level)) for level in raidlevels]


class RaidForm(Form):

    def __init__(self, all_devices, initial, raid_names):
        self.all_devices = all_devices
        self.raid_names = raid_names
        super().__init__(initial)

    name = StringField(_("Name:"))
    level = ChoiceField(_("RAID Level:"), choices=raidlevel_choices)
    devices = MultiDeviceField(_("Devices:"))
    size = ReadOnlyField(_("Size:"))

    def clean_name(self, val):
        if not re.match('md[0-9]+', val):
            val = 'md/' + val
        return val

    def validate_name(self):
        if self.name.value in self.raid_names:
            return _("There is already a RAID named '{}'").format(
                self.name.value)

    def validate_devices(self):
        log.debug(
            'validate_devices %s %s',
            len(self.devices.value), self.level.value)
        active_device_count = len(self.devices.widget.active_devices)
        if active_device_count < self.level.value.min_devices:
            return _(
                'RAID Level "{}" requires at least {} active devices').format(
                self.level.value.name, self.level.value.min_devices)


class RaidStretchy(Stretchy):
    def __init__(self, parent, existing=None):
        self.parent = parent
        self.existing = existing
        raid_names = {raid.name for raid in parent.model.all_raids()}
        if existing is None:
            title = _('Create software RAID ("MD") disk')
            x = 0
            while True:
                name = 'md{}'.format(x)
                if name not in raid_names:
                    break
                x += 1
            initial = {
                'devices': {},
                'name': name,
                'level': raidlevels_by_value[1],
                'size': '-',
                }
        else:
            raid_names.remove(existing.name)
            title = _('Edit software RAID disk "{}"').format(existing.name)
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

        all_devices = []

        cur_devices = set()
        if existing:
            cur_devices = existing.devices | existing.spare_devices

        def device_ok(dev):
            return dev != existing and (dev in cur_devices or dev.ok_for_raid)

        for dev in self.parent.model.all_devices():
            if device_ok(dev):
                all_devices.append((DEVICE, dev))
            else:
                ok_parts = []
                for part in dev.partitions():
                    if device_ok(part):
                        ok_parts.append((PART, part))
                if len(ok_parts) > 0:
                    all_devices.append((LABEL, dev))
                    all_devices.extend(ok_parts)

        form = self.form = RaidForm(all_devices, initial, raid_names)

        self.form.devices.widget.set_supports_spares(
            initial['level'].supports_spares)

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
