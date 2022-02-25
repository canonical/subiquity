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

from urwid import (
    connect_signal,
    Text,
    )

from subiquitycore.ui.container import (
    Pile,
    )
from subiquitycore.ui.form import (
    BooleanField,
    PasswordField,
    ReadOnlyField,
    simple_field,
    WantsToKnowFormField,
    )
from subiquitycore.ui.interactive import (
    StringEditor,
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
from subiquity.ui.views.identity import (
    setup_password_validation,
    )

log = logging.getLogger('subiquity.ui.views.filesystem.lvm')


class VGNameEditor(StringEditor, WantsToKnowFormField):
    def __init__(self):
        self.valid_char_pat = r'[-a-zA-Z0-9_+.]'
        self.error_invalid_char = _("The only characters permitted in the "
                                    "name of a volume group are a-z, A-Z, "
                                    "0-9, +, _, . and -")
        super().__init__()

    def valid_char(self, ch):
        if len(ch) == 1 and not re.match(self.valid_char_pat, ch):
            self.bff.in_error = True
            self.bff.show_extra(("info_error", self.error_invalid_char))
            return False
        else:
            return super().valid_char(ch)


VGNameField = simple_field(VGNameEditor)


class VolGroupForm(CompoundDiskForm):

    def __init__(self, model, possible_components, initial,
                 vg_names, deleted_vg_names):
        self.vg_names = vg_names
        self.deleted_vg_names = deleted_vg_names
        super().__init__(model, possible_components, initial)
        connect_signal(self.encrypt.widget, 'change', self._change_encrypt)
        setup_password_validation(self, _("passphrases"))
        self._change_encrypt(None, self.encrypt.value)

    name = VGNameField(_("Name:"))
    devices = MultiDeviceField(_("Devices:"))
    size = ReadOnlyField(_("Size:"))
    encrypt = BooleanField(_("Create encrypted volume"))
    password = PasswordField(_("Passphrase:"))
    confirm_password = PasswordField(_("Confirm passphrase:"))

    def _change_encrypt(self, sender, new_value):
        self.password.enabled = new_value
        self.confirm_password.enabled = new_value
        if not new_value:
            self.password.validate()
            self.confirm_password.validate()

    def validate_devices(self):
        if len(self.devices.value) < 1:
            return _("Select at least one device to be part of the volume "
                     "group.")

    def validate_name(self):
        v = self.name.value
        if not v:
            return _("The name of a volume group cannot be empty")
        if v.startswith('-'):
            return _("The name of a volume group cannot start with a hyphen")
        if v in self.vg_names:
            return _("There is already a volume group named '{name}'").format(
                name=self.name.value)
        if v in ('.', '..', 'md') or os.path.exists('/dev/' + v):
            if v not in self.deleted_vg_names:
                return _("{name} is not a valid name for a volume "
                         "group").format(name=v)

    def validate_password(self):
        if self.encrypt.value and len(self.password.value) < 1:
            return _("Passphrase must be set")

    def validate_confirm_password(self):
        if self.encrypt.value and \
          self.password.value != self.confirm_password.value:
            return _("Passphrases do not match")


class VolGroupStretchy(Stretchy):
    def __init__(self, parent, existing=None):
        self.parent = parent
        self.existing = existing
        vg_names = {vg.name for vg in parent.model.all_volgroups()}
        orig_vg_names = {
            action['name'] for action in parent.model._orig_config
            if action['type'] == 'lvm_volgroup'
            }
        if existing is None:
            title = _('Create LVM volume group')
            label = _('Create')
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
            title = _('Edit volume group "{name}"').format(name=existing.name)
            label = _('Save')
            devices = {}
            key = ""
            for d in existing.devices:
                if d.type == "dm_crypt":
                    key = d.key
                    d = d.volume
                devices[d] = 'active'
            initial = {
                'devices': devices,
                'name': existing.name,
                'encrypt': bool(key),
                'password': key,
                'confirm_password': key,
                }

        possible_components = get_possible_components(
            self.parent.model, existing, initial['devices'],
            lambda dev: dev.ok_for_lvm_vg)

        deleted_vg_names = orig_vg_names - vg_names
        form = self.form = VolGroupForm(
            self.parent.model, possible_components, initial,
            vg_names, deleted_vg_names)
        self.form.buttons.base_widget[0].set_label(label)

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
            self.form.size.value = humanize_size(get_lvm_size(new_devices))
        else:
            self.form.size.value = '-'

    def done(self, sender):
        result = self.form.as_data()
        del result['size']
        mdc = self.form.devices.widget
        result['devices'] = mdc.active_devices
        if 'confirm_password' in result:
            del result['confirm_password']
        safe_result = result.copy()
        if 'password' in safe_result:
            safe_result['password'] = '<REDACTED>'
        log.debug("vg_done: {}".format(safe_result))
        self.parent.controller.volgroup_handler(self.existing, result)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender):
        self.parent.remove_overlay()
