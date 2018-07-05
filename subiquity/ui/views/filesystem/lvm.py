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
    connect_signal,
    Text,
    )

from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.form import (
    ReadOnlyField,
    StringField,
    )
from subiquitycore.ui.stretchy import (
    Stretchy,
    )

from subiquity.models.filesystem import (
    get_lvm_size,
    humanize_size,
    )
from subiquity.ui.views.filesystem.compound import (
    CompoundDiskForm,
    get_possible_components,
    MultiDeviceField,
    )

log = logging.getLogger('subiquity.ui.lvm')


class VolGroupForm(CompoundDiskForm):

    def __init__(self, model, possible_components, initial, vg_names):
        self.vg_names = vg_names
        super().__init__(model, possible_components, initial)

    name = StringField(_("Name:"))
    devices = MultiDeviceField(_("Devices:"))
    size = ReadOnlyField(_("Size:"))

    def validate_name(self):
        if self.name.value in self.vg_names:
            return _("There is already a volume group named '{}'").format(
                self.name.value)


class VolGroupStretchy(Stretchy):
    def __init__(self, parent, existing=None):
        self.parent = parent
        self.existing = existing
        vg_names = {vg.name for vg in parent.model.all_vgs()}
        if existing is None:
            title = _('Create LVM volume group')
            x = 0
            while True:
                name = 'vg{}'.format(x)
                if name not in vg_names:
                    break
                x += 1
            initial = {
                'devices': {},
                'name': name,
                'size': '-',
                }
        else:
            vg_names.remove(existing.name)
            title = _('Edit volume group "{}"').format(existing.name)
            devices = {d:'active' for d in existing.devices}
            initial = {
                'devices': devices,
                'name': existing.name,
                }

        possible_components = get_possible_components(
            self.parent.model, existing, initial['devices'],
            lambda dev: dev.ok_for_lvm)

        form = self.form = VolGroupForm(
            self.parent.model, possible_components, initial, vg_names)

        self.form.devices.widget.set_supports_spares(False)

        connect_signal(form.devices.widget, 'change', self._change_devices)
        connect_signal(form, 'submit', self.done)
        connect_signal(form, 'cancel', self.cancel)

        rows = form.as_rows()

        super().__init__(
            title,
            [Pile(rows), Text(""), self.form.buttons],
            0, 0)

    def _change_devices(self, sender, new_devices):
        if len(sender.active_devices) >= 1:
            self.form.size.value = humanize_size(
                get_lvm_size(self.form.level.value.value, new_devices))
        else:
            self.form.size.value = '-'

    def done(self, sender):
        result = self.form.as_data()
        mdc = self.form.devices.widget
        result['devices'] = mdc.active_devices
        result['spare_devices'] = mdc.spare_devices
        log.debug('vg_done: result = {}'.format(result))
        self.parent.controller.volgroup_handler(self.existing, result)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender):
        self.parent.remove_overlay()
