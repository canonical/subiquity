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

from urwid import (
    CheckBox,
    connect_signal,
    Padding as UrwidPadding,
    Text,
    )

from subiquitycore.ui.container import (
    WidgetWrap,
    )
from subiquitycore.ui.form import (
    Form,
    simple_field,
    Toggleable,
    WantsToKnowFormField,
    )
from subiquitycore.ui.selector import (
    Selector,
    )
from subiquitycore.ui.table import (
    TablePile,
    TableRow,
    )
from subiquitycore.ui.utils import (
    Color,
    )

from subiquity.models.filesystem import (
    humanize_size,
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
        for kind, device in bff.form.possible_components:
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


class CompoundDiskForm(Form):

    def __init__(self, model, possible_components, initial):
        self.model = model
        self.possible_components = possible_components
        super().__init__(initial)

    def validate_devices(self):
        if not self.model.has_bootloader_partition():
            mdc = self.devices.widget
            empty_disks = {d for d in self.model.all_disks() if d.used == 0}
            if not empty_disks - set(mdc.value):
                return _("\
If you put all disks into RAIDs or LVM VGs, there will be nowhere \
to put the boot partition.")


def get_possible_components(model, existing, cur_devices, device_ok):

    possible_components = []

    def check(dev):
        return dev != existing and (dev in cur_devices or device_ok(dev))

    for dev in model.all_devices():
        if check(dev):
            possible_components.append((DEVICE, dev))
        else:
            ok_parts = []
            for part in dev.partitions():
                if device_ok(part):
                    ok_parts.append((PART, part))
            if len(ok_parts) > 0:
                possible_components.append((LABEL, dev))
                possible_components.extend(ok_parts)

    return possible_components
