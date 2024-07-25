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
import pathlib
import re

from urwid import Text, connect_signal

from subiquity.models.filesystem import RecoveryKeyHandler, get_lvm_size, humanize_size
from subiquity.ui.views.filesystem.compound import (
    CompoundDiskForm,
    MultiDeviceField,
    get_possible_components,
)
from subiquitycore.async_helpers import connect_async_signal
from subiquitycore.ui.container import Pile
from subiquitycore.ui.form import (
    BooleanField,
    PasswordField,
    ReadOnlyField,
    WantsToKnowFormField,
    simple_field,
)
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.stretchy import Stretchy

log = logging.getLogger("subiquity.ui.views.filesystem.lvm")


class VGNameEditor(StringEditor, WantsToKnowFormField):
    def __init__(self):
        self.valid_char_pat = r"[-a-zA-Z0-9_+.]"
        self.error_invalid_char = _(
            "The only characters permitted in the "
            "name of a volume group are a-z, A-Z, "
            "0-9, +, _, . and -"
        )
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
    def __init__(self, model, possible_components, initial, vg_names, deleted_vg_names):
        self.vg_names = vg_names
        self.deleted_vg_names = deleted_vg_names
        super().__init__(model, possible_components, initial)
        connect_signal(self.encrypt.widget, "change", self._change_encrypt)
        self.confirm_passphrase.use_as_confirmation(
            for_field=self.passphrase, desc=_("Passphrases")
        )
        self._change_encrypt(None, self.encrypt.value)

    name = VGNameField(_("Name:"))
    devices = MultiDeviceField(_("Devices:"))
    size = ReadOnlyField(_("Size:"))
    encrypt = BooleanField(_("Create encrypted volume"))
    passphrase = PasswordField(_("Passphrase:"))
    confirm_passphrase = PasswordField(_("Confirm passphrase:"))
    # TODO replace the placeholders in the help - also potentially replacing
    # "~" with the actual home directory.
    create_recovery_key = BooleanField(
        _("Also create a recovery key:"),
        help=_(
            "The key will be stored as"
            " ~/recovery-key-{name}.txt in the live system and will"
            " be copied to /var/log/installer/ in the target"
            " system."
        ),
    )

    def _change_encrypt(self, sender, new_value):
        self.passphrase.enabled = new_value
        self.confirm_passphrase.enabled = new_value
        self.create_recovery_key.enabled = new_value
        if not new_value:
            self.passphrase.validate()
            self.confirm_passphrase.validate()

    def validate_devices(self):
        if len(self.devices.value) < 1:
            return _("Select at least one device to be part of the volume group.")

    def validate_name(self):
        v = self.name.value
        if not v:
            return _("The name of a volume group cannot be empty")
        if v.startswith("-"):
            return _("The name of a volume group cannot start with a hyphen")
        if v in self.vg_names:
            return _("There is already a volume group named '{name}'").format(
                name=self.name.value
            )
        if v in (".", "..", "md") or os.path.exists("/dev/" + v):
            if v not in self.deleted_vg_names:
                return _("{name} is not a valid name for a volume group").format(name=v)

    def validate_passphrase(self):
        if self.encrypt.value and len(self.passphrase.value) < 1:
            return _("Passphrase must be set")

    def validate_confirm_passphrase(self):
        if (
            self.encrypt.value
            and self.passphrase.value != self.confirm_passphrase.value
        ):
            return _("Passphrases do not match")


class VolGroupStretchy(Stretchy):
    def __init__(self, parent, existing=None):
        self.parent = parent
        self.existing = existing
        vg_names = {vg.name for vg in parent.model.all_volgroups()}
        orig_vg_names = {
            action["name"]
            for action in parent.model._orig_config
            if action["type"] == "lvm_volgroup"
        }
        if existing is None:
            title = _("Create LVM volume group")
            label = _("Create")
            x = 0
            while True:
                name = "vg{}".format(x)
                if name not in vg_names:
                    break
                x += 1
            initial = {
                "devices": {},
                "name": name,
                "size": "-",
            }
        else:
            vg_names.remove(existing.name)
            title = _('Edit volume group "{name}"').format(name=existing.name)
            label = _("Save")
            devices = {}
            key = ""
            encrypt = False
            create_recovery_key = False
            for d in existing.devices:
                if d.type == "dm_crypt":
                    encrypt = True
                    # If the DM_Crypt object was created using information
                    # sent by the server (this happens when the passphrase was
                    # provided in the Guided Storage screen), it will not
                    # contain a key but a path to a keyfile (d.keyfile). The
                    # client may not have permission to read the keyfile so it
                    # seems simpler to just present an empty passphrase field
                    # and ask the user to fill the passphrase again if they
                    # want to make adjustments to the VG.
                    # TODO make this more user friendly.
                    if d.key is not None:
                        key = d.key
                    create_recovery_key = d.recovery_key is not None
                    d = d.volume
                devices[d] = "active"
            initial = {
                "devices": devices,
                "name": existing.name,
                "encrypt": encrypt,
                "passphrase": key,
                "confirm_passphrase": key,
                "create_recovery_key": create_recovery_key,
            }

        possible_components = get_possible_components(
            self.parent.model,
            existing,
            initial["devices"],
            lambda dev: dev.ok_for_lvm_vg,
        )

        deleted_vg_names = orig_vg_names - vg_names
        form = self.form = VolGroupForm(
            self.parent.model, possible_components, initial, vg_names, deleted_vg_names
        )
        self.form.buttons.base_widget[0].set_label(label)

        self.form.devices.widget.set_supports_spares(False)

        connect_signal(form.devices.widget, "change", self._change_devices)
        connect_async_signal(form, "submit", self.done)
        connect_signal(form, "cancel", self.cancel)

        rows = form.as_rows()

        super().__init__(title, [Pile(rows), Text(""), self.form.buttons], 0, 0)

    def _change_devices(self, sender, new_devices):
        if len(sender.active_devices) >= 1:
            self.form.size.value = humanize_size(get_lvm_size(new_devices))
        else:
            self.form.size.value = "-"

    async def done(self, sender):
        result = self.form.as_data()
        del result["size"]
        mdc = self.form.devices.widget
        result["devices"] = mdc.active_devices
        if "create_recovery_key" in result:
            if result["create_recovery_key"]:
                backup_prefix = pathlib.Path("/var/log/installer")
                filename = pathlib.Path(f"recovery-key-{result['name']}.txt")
                result["recovery-key"] = RecoveryKeyHandler(
                    live_location=pathlib.Path("~").expanduser() / filename,
                    backup_location=backup_prefix / filename,
                )
            del result["create_recovery_key"]
        if "confirm_passphrase" in result:
            del result["confirm_passphrase"]
        safe_result = result.copy()
        if "passphrase" in safe_result:
            safe_result["passphrase"] = "<REDACTED>"
        log.debug("vg_done: {}".format(safe_result))
        await self.parent.controller.volgroup_handler(self.existing, result)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()

    def cancel(self, sender):
        self.parent.remove_overlay()
