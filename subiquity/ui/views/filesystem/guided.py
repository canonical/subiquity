# Copyright 2017 Canonical, Ltd.
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
from urwid import Text, connect_signal

from subiquity.common.types import (
    Gap,
    GuidedCapability,
    GuidedChoiceV2,
    GuidedDisallowedCapabilityReason,
    GuidedStorageTargetManual,
    GuidedStorageTargetReformat,
    Partition,
)
from subiquity.models.filesystem import humanize_size
from subiquitycore.ui.buttons import other_btn
from subiquitycore.ui.form import (
    NO_CAPTION,
    NO_HELP,
    BooleanField,
    ChoiceField,
    Form,
    PasswordField,
    RadioButtonField,
    SubForm,
    SubFormField,
)
from subiquitycore.ui.selector import Option
from subiquitycore.ui.table import TablePile, TableRow
from subiquitycore.ui.utils import Color, rewrap, screen
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.filesystem.guided")

subtitle = _("Configure a guided storage layout, or create a custom one:")


class LUKSOptionsForm(SubForm):
    passphrase = PasswordField(_("Passphrase:"))
    confirm_passphrase = PasswordField(_("Confirm passphrase:"))

    def validate_passphrase(self):
        if len(self.passphrase.value) < 1:
            return _("Passphrase must be set")

    def validate_confirm_passphrase(self):
        if self.passphrase.value != self.confirm_passphrase.value:
            return _("Passphrases do not match")


class LVMOptionsForm(SubForm):
    def __init__(self, parent):
        super().__init__(parent)
        connect_signal(self.encrypt.widget, "change", self._toggle)
        self.luks_options.enabled = self.encrypt.value

    def _toggle(self, sender, val):
        self.luks_options.enabled = val
        self.validated()

    encrypt = BooleanField(_("Encrypt the LVM group with LUKS"), help=NO_HELP)
    luks_options = SubFormField(LUKSOptionsForm, "", help=NO_HELP)


def summarize_device(disk):
    label = disk.label
    rows = [
        (
            disk,
            [
                (2, Text(label)),
                Text(disk.type),
                Text(humanize_size(disk.size), align="right"),
            ],
        )
    ]
    if disk.partitions:
        for part in disk.partitions:
            if isinstance(part, Partition):
                details = ", ".join(part.annotations)
                rows.append(
                    (
                        part,
                        [
                            Text(_("partition {number}").format(number=part.number)),
                            (2, Text(details)),
                            Text(humanize_size(part.size), align="right"),
                        ],
                    )
                )
            elif isinstance(part, Gap):
                # If desired, we could show gaps here.  It is less critical,
                # given that the context is reformatting full disks and the
                # partition display is showing what is about to be lost.
                pass
            else:
                raise Exception(f"unhandled partition type {part}")
    else:
        rows.append((None, [(4, Color.info_minor(Text(", ".join(disk.usage_labels))))]))
    return rows


@attr.s(auto_attribs=True)
class TPMChoice:
    enabled: bool
    default: bool
    help: str


tpm_help_texts = {
    "AVAILABLE_CAN_BE_DESELECTED": _(
        "The entire disk will be encrypted and protected by the "
        "TPM. If this option is deselected, the disk will be "
        "unencrypted and without any protection."
    ),
    "AVAILABLE_CANNOT_BE_DESELECTED": _(
        "The entire disk will be encrypted and protected by the TPM."
    ),
    "UNAVAILABLE":
    # for translators: 'reason' is the reason FDE is unavailable.
    _(
        "TPM backed full-disk encryption is not available "
        'on this device (the reason given was "{reason}").'
    ),
}

choices = {
    GuidedCapability.CORE_BOOT_ENCRYPTED: TPMChoice(
        enabled=False,
        default=True,
        help=tpm_help_texts["AVAILABLE_CANNOT_BE_DESELECTED"],
    ),
    GuidedCapability.CORE_BOOT_UNENCRYPTED: TPMChoice(
        enabled=False, default=False, help=tpm_help_texts["UNAVAILABLE"]
    ),
    GuidedCapability.CORE_BOOT_PREFER_ENCRYPTED: TPMChoice(
        enabled=True, default=True, help=tpm_help_texts["AVAILABLE_CAN_BE_DESELECTED"]
    ),
    GuidedCapability.CORE_BOOT_PREFER_UNENCRYPTED: TPMChoice(
        enabled=True, default=False, help=tpm_help_texts["AVAILABLE_CAN_BE_DESELECTED"]
    ),
}


class GuidedChoiceForm(SubForm):
    disk = ChoiceField(caption=NO_CAPTION, help=NO_HELP, choices=["x"])
    use_lvm = BooleanField(_("Set up this disk as an LVM group"), help=NO_HELP)
    lvm_options = SubFormField(LVMOptionsForm, "", help=NO_HELP)
    use_tpm = BooleanField(_("Full disk encryption with TPM"))

    def __init__(self, parent):
        super().__init__(parent, initial={"use_lvm": True})
        self.tpm_choice = None

        options = []
        tables = []
        initial = -1

        all_caps = set()

        for target in parent.targets:
            all_caps.update(target.allowed)
            all_caps.update(d.capability for d in target.disallowed)
            disk = parent.disk_by_id[target.disk_id]
            for obj, cells in summarize_device(disk):
                table = TablePile([TableRow(cells)])
                tables.append(table)
                if obj is disk and target.allowed:
                    if initial < 0:
                        initial = len(options)
                    val = target
                else:
                    val = None
                options.append(Option((table, val is not None, val)))

        t0 = tables[0]
        for t in tables[1:]:
            t0.bind(t)

        self.disk.widget.options = options
        self.disk.widget.index = initial
        connect_signal(self.disk.widget, "select", self._select_disk)
        self._select_disk(None, self.disk.value)
        connect_signal(self.use_lvm.widget, "change", self._toggle_lvm)
        self._toggle_lvm(None, self.use_lvm.value)

        if GuidedCapability.LVM_LUKS not in all_caps:
            self.remove_field("lvm_options")
        if GuidedCapability.LVM not in all_caps:
            self.remove_field("use_lvm")
        core_boot_caps = [c for c in all_caps if c.is_core_boot()]
        if not core_boot_caps:
            self.remove_field("use_tpm")

    def _select_disk(self, sender, val):
        self.use_lvm.enabled = GuidedCapability.LVM in val.allowed
        core_boot_caps = [c for c in val.allowed if c.is_core_boot()]
        if core_boot_caps:
            assert len(val.allowed) == 1
            cap = core_boot_caps[0]
            reason = ""
            for disallowed in val.disallowed:
                if disallowed.capability == GuidedCapability.CORE_BOOT_ENCRYPTED:
                    reason = disallowed.message
            self.tpm_choice = choices[cap]
            self.use_tpm.enabled = self.tpm_choice.enabled
            self.use_tpm.value = self.tpm_choice.default
            self.use_tpm.help = self.tpm_choice.help
            self.use_tpm.help = self.tpm_choice.help.format(reason=reason)
        else:
            self.tpm_choice = None

    def _toggle_lvm(self, sender, val):
        self.lvm_options.enabled = val
        self.validated()


class GuidedForm(Form):
    group = []

    guided = RadioButtonField(group, _("Use an entire disk"), help=NO_HELP)
    guided_choice = SubFormField(GuidedChoiceForm, "", help=NO_HELP)
    custom = RadioButtonField(group, _("Custom storage layout"), help=NO_HELP)

    cancel_label = _("Back")

    def __init__(self, targets, disk_by_id):
        self.targets = targets
        self.disk_by_id = disk_by_id
        super().__init__()
        connect_signal(self.guided.widget, "change", self._toggle_guided)

    def _toggle_guided(self, sender, new_value):
        self.guided_choice.enabled = new_value
        self.validated()


HELP = _(
    """

The "Use an entire disk" option installs Ubuntu onto the selected disk,
replacing any partitions and data already there.

If the platform requires it, a bootloader partition is created on the disk.

If you choose to use LVM, two additional partitions are then created,
one for /boot and one covering the rest of the disk. An LVM volume
group is created containing the large partition. A logical volume is
created for the root filesystem, sized using some simple heuristic. It
can easily be enlarged with standard LVM command line tools (or on the
next screen).

You can also choose to encrypt LVM volume group. This will require
setting a passphrase, that one will need to type on every boot before
the system boots.

If you do not choose to use LVM, a single partition is created covering the
rest of the disk which is then formatted as ext4 and mounted at /.

In either case, you will still have a chance to review and modify the results.

If you choose to use a custom storage layout, no changes are made to the disks
and you will have to, at a minimum, select a boot disk and mount a filesystem
at /.

"""
)


no_big_disks = _(
    """
Block probing did not discover any disks big enough to support guided storage
configuration. Manual configuration may still be possible.
"""
)


no_disks = _(
    """
Block probing did not discover any disks. Unfortunately this means that
installation will not be possible.
"""
)


class GuidedDiskSelectionView(BaseView):
    title = _("Guided storage configuration")

    def __init__(self, controller, targets, disk_by_id):
        self.controller = controller

        reformats = []
        any_ok = False
        offer_manual = False
        encryption_unavail_reason = ""
        GCDR = GuidedDisallowedCapabilityReason

        for target in targets:
            if isinstance(target, GuidedStorageTargetManual):
                offer_manual = True
            if not isinstance(target, GuidedStorageTargetReformat):
                continue
            reformats.append(target)
            if target.allowed:
                any_ok = True
            for disallowed in target.disallowed:
                if disallowed.reason == GCDR.CORE_BOOT_ENCRYPTION_UNAVAILABLE:
                    encryption_unavail_reason = disallowed.message

        if any_ok:
            show_form = self.form = GuidedForm(targets=reformats, disk_by_id=disk_by_id)

            if not offer_manual:
                show_form = self.form.guided_choice.widget.form
                excerpt = _("Choose a disk to install to:")
            else:
                excerpt = _(subtitle)

            connect_signal(show_form, "submit", self.done)
            connect_signal(show_form, "cancel", self.cancel)

            super().__init__(
                show_form.as_screen(focus_buttons=False, excerpt=_(excerpt))
            )
        elif encryption_unavail_reason:
            super().__init__(
                screen(
                    [Text(rewrap(_(encryption_unavail_reason)))],
                    [other_btn(_("Back"), on_press=self.cancel)],
                    excerpt=_("Cannot install core boot classic system"),
                )
            )
        elif disk_by_id and offer_manual:
            super().__init__(
                screen(
                    [Text(rewrap(_(no_big_disks)))],
                    [
                        other_btn(_("OK"), on_press=self.manual),
                        other_btn(_("Back"), on_press=self.cancel),
                    ],
                )
            )
        else:
            super().__init__(screen([Text(rewrap(_(no_disks)))], []))

    def local_help(self):
        return (_("Help on guided storage configuration"), rewrap(_(HELP)))

    def done(self, sender):
        results = self.form.as_data()
        if results["guided"]:
            guided_choice = results["guided_choice"]
            target = guided_choice["disk"]
            tpm_choice = self.form.guided_choice.widget.form.tpm_choice
            password = None
            if tpm_choice is not None:
                if guided_choice.get("use_tpm", tpm_choice.default):
                    capability = GuidedCapability.CORE_BOOT_ENCRYPTED
                else:
                    capability = GuidedCapability.CORE_BOOT_UNENCRYPTED
            elif guided_choice.get("use_lvm", False):
                opts = guided_choice.get("lvm_options", {})
                if opts.get("encrypt", False):
                    capability = GuidedCapability.LVM_LUKS
                    password = opts["luks_options"]["passphrase"]
                else:
                    capability = GuidedCapability.LVM
            else:
                capability = GuidedCapability.DIRECT
            choice = GuidedChoiceV2(
                target=target,
                capability=capability,
                password=password,
            )
        else:
            choice = GuidedChoiceV2(
                target=GuidedStorageTargetManual(),
                capability=GuidedCapability.MANUAL,
            )
        self.controller.guided_choice(choice)

    def manual(self, sender):
        self.controller.guided_choice(
            GuidedChoiceV2(
                target=GuidedStorageTargetManual(),
                capability=GuidedCapability.MANUAL,
            )
        )

    def cancel(self, btn=None):
        self.controller.cancel()
