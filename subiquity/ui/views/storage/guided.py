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
import pathlib
from typing import Optional

from urwid import Divider, Padding, Text, connect_signal

from subiquity.common.types.storage import (
    Disk,
    Gap,
    GuidedCapability,
    GuidedChoiceV2,
    GuidedDisallowedCapabilityReason,
    GuidedStorageTarget,
    GuidedStorageTargetEraseInstall,
    GuidedStorageTargetManual,
    GuidedStorageTargetReformat,
    GuidedStorageTargetResize,
    GuidedStorageTargetUseGap,
    Partition,
    RecoveryKey,
)
from subiquity.models.storage import humanize_size
from subiquitycore.ui.buttons import forward_btn, other_btn
from subiquitycore.ui.container import ListBox
from subiquitycore.ui.form import (
    NO_CAPTION,
    NO_HELP,
    BooleanField,
    ChoiceField,
    Form,
    PasswordField,
    RadioButtonField,
)
from subiquitycore.ui.selector import Option
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.table import TablePile, TableRow
from subiquitycore.ui.utils import Color, rewrap, screen
from subiquitycore.view import BaseView

log = logging.getLogger("subiquity.ui.views.storage.guided")


def summarize_device(disk):
    label = disk.label
    rows = [
        (
            # Partial reformat is only supported when using the storage v2 API.
            # Skip scenarios that have in-use partitions.
            disk if not disk.has_in_use_partition else None,
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


HELP = _("""

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

""")


no_big_disks = _("""
Block probing did not discover any disks big enough to support guided storage
configuration. Manual configuration may still be possible.
""")


no_disks = _("""
Block probing did not discover any disks. Unfortunately this means that
installation will not be possible.
""")


class CapabilitySelectionStretchy(Stretchy):
    def __init__(
        self, parent: "GuidedDiskSelectionViewV2Debug", *, target, allowed_capabilities
    ) -> None:
        self.parent = parent
        self.target = target

        buttons = []
        for cap in allowed_capabilities:
            label = cap.name.replace("_", " ").title()
            buttons.append(
                forward_btn(label=label, on_press=self.proceed, user_arg=cap)
            )

        return super().__init__("Capability", buttons, 0, 0)

    def proceed(self, sender, cap: GuidedCapability):
        self.parent.controller.guided_choice(
            GuidedChoiceV2(target=self.target, capability=cap)
        )


class GuidedDiskSelectionViewV2Debug(BaseView):
    title = "Guided storage configuration for storage version 2 (only for debugging)"

    desc = """
/!\\ This view is only for debugging. Its goal is to make it easier to reproduce \
some storage-version=2 bugs that may have occurred using the desktop installer.

Considerations:
 * The view is incomplete, has no translations, might crash in some scenarios, use \
it at your own risk...
 * Parameters of allowed capabilities (e.g., passphrase for LVM+LUKS) are not supported.
 * For target resize, the recommended size will be used (no slider is implemented).
 """

    def __init__(
        self,
        controller,
        targets: list[GuidedStorageTarget],
        disk_by_id: dict[str, Disk],
    ):
        self.controller = controller

        buttons = []

        for target in targets:
            if isinstance(target, GuidedStorageTargetManual):
                label = "Manual partitioning"
            elif isinstance(target, GuidedStorageTargetReformat):
                label = "Install to {} after wiping it".format(target.disk_id)
            elif isinstance(target, GuidedStorageTargetUseGap):
                label = "Install to {} in {} gap at offset {}".format(
                    target.disk_id,
                    humanize_size(target.gap.size),
                    target.gap.offset,
                )
            elif isinstance(
                target, (GuidedStorageTargetEraseInstall, GuidedStorageTargetResize)
            ):
                partition = next(
                    iter(
                        [
                            p
                            for p in disk_by_id[target.disk_id].partitions
                            if isinstance(p, Partition)
                            and p.number == target.partition_number
                        ]
                    )
                )
                if isinstance(target, GuidedStorageTargetEraseInstall):
                    label = (
                        "Install to {} after erasing p{} ({}) which contains {}".format(
                            target.disk_id,
                            partition.number,
                            humanize_size(partition.size),
                            partition.os,
                        )
                    )
                else:
                    label = (
                        "Install to {} after resizing p{} (currently {}) to {}".format(
                            target.disk_id,
                            partition.number,
                            humanize_size(partition.size),
                            humanize_size(target.recommended),
                        )
                    )
            else:
                label = f"Unsupported scenario ({type(target)})"

            buttons.append(
                forward_btn(label=label, on_press=self.proceed, user_arg=target)
            )

        return super().__init__(
            screen(
                ListBox(buttons),
                focus_buttons=False,
                narrow_rows=True,
                buttons=None,
                excerpt=self.desc,
            )
        )

    def proceed(self, sender, target: GuidedStorageTarget):
        if isinstance(target, GuidedStorageTargetManual):
            self.controller.guided_choice(
                GuidedChoiceV2(target=target, capability=GuidedCapability.MANUAL)
            )
        elif isinstance(
            target,
            (
                GuidedStorageTargetReformat,
                GuidedStorageTargetUseGap,
                GuidedStorageTargetEraseInstall,
                GuidedStorageTargetResize,
            ),
        ):
            if isinstance(target, GuidedStorageTargetResize):
                # Feel free to add a slider or something to configure the size...
                target.new_size = target.recommended
            # The overlay will call the controller or close itself
            self.show_stretchy_overlay(
                CapabilitySelectionStretchy(
                    parent=self, target=target, allowed_capabilities=target.allowed
                )
            )


# ┌ Guided storage configuration ──────────────────────────────────────┐
# │                                                                    │
# │  Choose a disk to install to, and how to install on it:            │
# │                                                                    │
# │  Disk:  [ sda  local disk  500.000G  ▾ ]                           │
# │                                                                    │
# │  How to install:                                                   │
# │                                                                    │
# │    ( )  Guided — use entire disk                                   │
# │                                                                    │
# │    (X)  Guided — use entire disk with LVM  (encryption optional)   │
# │         You can choose to encrypt the LVM group with LUKS on the   │
# │         next screen.                                               │
# │                                                                    │
# │    ( )  Full disk encryption with TPM                              │
# │         The entire disk will be encrypted and protected by the     │
# │         TPM.                                                       │
# │                                                                    │
# │    ( )  Core boot classic — no encryption                          │
# │         The disk will not be encrypted.                            │
# │                                                                    │
# │    ( )  Custom storage layout                                      │
# │                                                                    │
# │                          [ Continue ]   [ Back ]                   │
# └────────────────────────────────────────────────────────────────────┘


guided_subtitle = _("Choose a disk to install to, and how to install on it:")

tpm_help_texts = {
    "ENCRYPTED": _("The entire disk will be encrypted and protected by the TPM."),
    "UNENCRYPTED": _("The disk will not be encrypted."),
}


class GuidedForm(Form):
    group = []

    disk = ChoiceField(caption=NO_CAPTION, help=NO_HELP, choices=["x"])
    choice_direct = RadioButtonField(group, _("Guided — use entire disk"), help=NO_HELP)
    choice_lvm = RadioButtonField(
        group,
        _("Guided — use entire disk with LVM  (encryption optional)"),
        help=_("You can choose to encrypt the LVM group with LUKS on the next screen."),
    )
    choice_core_boot_classic_encrypted = RadioButtonField(
        group, _("Full disk encryption with TPM"), help=""
    )
    choice_core_boot_classic_unencrypted = RadioButtonField(
        group, _("No encryption"), help=""
    )
    choice_custom = RadioButtonField(group, _("Custom storage layout"), help=NO_HELP)

    ok_label = _("Continue")
    cancel_label = _("Back")

    def __init__(self, targets, disk_by_id, offer_manual):
        self.targets = targets
        self.disk_by_id = disk_by_id
        self.offer_manual = offer_manual
        super().__init__()

        options = []
        tables = []
        initial = -1

        all_caps = set()
        for target in targets:
            all_caps.update(target.allowed)
            all_caps.update(d.capability for d in target.disallowed)
            disk = disk_by_id[target.disk_id]
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

        # View-level radio presence: a radio is shown only if at least one
        # target supports the corresponding capability.
        if not (GuidedCapability.DIRECT in all_caps or GuidedCapability.DD in all_caps):
            self.remove_field("choice_direct")
        if not (
            GuidedCapability.LVM in all_caps or GuidedCapability.LVM_LUKS in all_caps
        ):
            self.remove_field("choice_lvm")
        if not any(c.is_core_boot() for c in all_caps):
            self.remove_field("choice_core_boot_classic_encrypted")
            self.remove_field("choice_core_boot_classic_unencrypted")
        elif {c for c in all_caps if c.is_core_boot()} == {
            GuidedCapability.CORE_BOOT_ENCRYPTED
        }:
            self.remove_field("choice_core_boot_classic_unencrypted")
        if not offer_manual:
            self.remove_field("choice_custom")

        # During construction the radios are in urwid's default state (the
        # first one selected), which is not a real user choice. Apply the real
        # default for the initially-selected disk; later (user-driven) disk
        # changes preserve the current selection when still valid.
        self._initialized = False
        self._select_disk(None, self.disk.value)
        self._initialized = True

    def _field_present(self, name):
        return any(bf.field.name == name for bf in self._fields)

    def _select_disk(self, sender, val):
        if val is None:
            for name in (
                "choice_direct",
                "choice_lvm",
                "choice_core_boot_classic_encrypted",
                "choice_core_boot_classic_unencrypted",
            ):
                if self._field_present(name):
                    getattr(self, name).enabled = False
            self.validated()
            return

        direct_ok = (
            GuidedCapability.DIRECT in val.allowed or GuidedCapability.DD in val.allowed
        )
        lvm_ok = (
            GuidedCapability.LVM in val.allowed
            or GuidedCapability.LVM_LUKS in val.allowed
        )

        if self._field_present("choice_direct"):
            self.choice_direct.enabled = direct_ok
        if self._field_present("choice_lvm"):
            self.choice_lvm.enabled = lvm_ok

        core_boot_caps = [c for c in val.allowed if c.is_core_boot()]
        disallowed_encrypted_reason = ""
        for d in val.disallowed:
            if d.capability == GuidedCapability.CORE_BOOT_ENCRYPTED:
                disallowed_encrypted_reason = d.message

        has_classic = (
            GuidedCapability.DIRECT in val.allowed
            or GuidedCapability.DD in val.allowed
            or GuidedCapability.LVM in val.allowed
            or GuidedCapability.LVM_LUKS in val.allowed
        )

        if self._field_present("choice_core_boot_classic_encrypted"):
            if core_boot_caps:
                cap = core_boot_caps[0]
                if cap == GuidedCapability.CORE_BOOT_UNENCRYPTED:
                    self.choice_core_boot_classic_encrypted.enabled = False
                    self.choice_core_boot_classic_encrypted.help = (
                        disallowed_encrypted_reason
                    )
                else:
                    self.choice_core_boot_classic_encrypted.enabled = True
                    self.choice_core_boot_classic_encrypted.help = tpm_help_texts[
                        "ENCRYPTED"
                    ]
            else:
                self.choice_core_boot_classic_encrypted.enabled = False

        if self._field_present("choice_core_boot_classic_unencrypted"):
            if core_boot_caps:
                cap = core_boot_caps[0]
                if cap == GuidedCapability.CORE_BOOT_ENCRYPTED:
                    self.choice_core_boot_classic_unencrypted.enabled = False
                else:
                    self.choice_core_boot_classic_unencrypted.enabled = True
                    if has_classic:
                        self.choice_core_boot_classic_unencrypted.widget.set_label(
                            _("Core boot classic — no encryption")
                        )
                    else:
                        self.choice_core_boot_classic_unencrypted.widget.set_label(
                            _("No encryption")
                        )
                    self.choice_core_boot_classic_unencrypted.help = tpm_help_texts[
                        "UNENCRYPTED"
                    ]
            else:
                self.choice_core_boot_classic_unencrypted.enabled = False

        # Preserve the user's current radio selection when it is still valid for
        # the newly selected disk; only fall back to a default when the current
        # selection is no longer enabled (or none was selected). On the initial
        # setup (before the user has chosen anything) always apply the default.
        current = self._current_selection()
        if self._initialized and current is not None and current.enabled:
            pass
        else:
            self._select_default(val)
        self.validated()

    def _current_selection(self):
        for name in (
            "choice_core_boot_classic_encrypted",
            "choice_core_boot_classic_unencrypted",
            "choice_lvm",
            "choice_direct",
            "choice_custom",
        ):
            if self._field_present(name) and getattr(self, name).value:
                return getattr(self, name)
        return None

    def _select_default(self, val):
        # Priority: core-boot encrypted > core-boot unencrypted > LVM > direct
        # > custom. This preserves the former defaults (use_tpm=True for
        # core-boot disks, use_lvm=True for classic disks). Use
        # widget.set_state(True) (not .value = True) so the radio group's other
        # members are deselected (urwid's `state` property setter bypasses
        # RadioButton.set_state's group handling).
        target = None
        core_boot_caps = [c for c in val.allowed if c.is_core_boot()]
        if core_boot_caps:
            cap = core_boot_caps[0]
            if cap == GuidedCapability.CORE_BOOT_ENCRYPTED:
                target = self.choice_core_boot_classic_encrypted
            elif cap == GuidedCapability.CORE_BOOT_PREFER_ENCRYPTED:
                target = self.choice_core_boot_classic_encrypted
            elif cap == GuidedCapability.CORE_BOOT_PREFER_UNENCRYPTED:
                target = self.choice_core_boot_classic_unencrypted
            elif cap == GuidedCapability.CORE_BOOT_UNENCRYPTED:
                target = self.choice_core_boot_classic_unencrypted
        elif self._field_present("choice_lvm") and self.choice_lvm.enabled:
            target = self.choice_lvm
        elif self._field_present("choice_direct") and self.choice_direct.enabled:
            target = self.choice_direct
        elif self._field_present("choice_custom"):
            target = self.choice_custom
        if target is not None:
            target.widget.set_state(True)

    def as_screen(self, focus_buttons=True, excerpt=None, narrow_rows=False):
        # Custom layout: the disk selector, then a "How to install:" section
        # title, then the capability radios indented under it (mirroring the
        # wireframe). The radio tables are bound together so their columns
        # align.
        rows = [
            self.disk._table,
            Divider(),
            Text(_("How to install:")),
        ]
        radio_names = [
            "choice_direct",
            "choice_lvm",
            "choice_core_boot_classic_encrypted",
            "choice_core_boot_classic_unencrypted",
            "choice_custom",
        ]
        radio_t0 = None
        for name in radio_names:
            if not self._field_present(name):
                continue
            bf = getattr(self, name)
            if radio_t0 is None:
                radio_t0 = bf._table
            else:
                radio_t0.bind(bf._table)
            rows.append(Divider())
            rows.append(Padding(bf._table, left=2))
        return screen(
            rows,
            self.buttons,
            focus_buttons=focus_buttons,
            excerpt=excerpt,
            narrow_rows=narrow_rows,
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
            # v2 guided will advertise "partial" reformat scenarios (i.e.,
            # where at least one partition is in use). We don't want to offer
            # that in v1 guided so check for in-use partitions.
            if target.allowed and not disk_by_id[target.disk_id].has_in_use_partition:
                any_ok = True
            for disallowed in target.disallowed:
                if disallowed.reason == GCDR.CORE_BOOT_ENCRYPTION_UNAVAILABLE:
                    encryption_unavail_reason = disallowed.message

        if any_ok:
            self.form = GuidedForm(
                targets=reformats, disk_by_id=disk_by_id, offer_manual=offer_manual
            )
            connect_signal(self.form, "submit", self.done)
            connect_signal(self.form, "cancel", self.cancel)
            super().__init__(
                self.form.as_screen(focus_buttons=False, excerpt=_(guided_subtitle))
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
            super().__init__(
                screen(
                    [Text(rewrap(_(no_disks)))],
                    [
                        other_btn(_("Back"), on_press=self.cancel),
                        other_btn(_("Refresh"), on_press=self.refresh),
                    ],
                )
            )

    def local_help(self):
        return (_("Help on guided storage configuration"), rewrap(_(HELP)))

    def done(self, sender):
        form = self.form
        target: GuidedStorageTargetReformat = form.disk.value

        if form._field_present("choice_custom") and form.choice_custom.value:
            self.controller.guided_choice(
                GuidedChoiceV2(
                    target=GuidedStorageTargetManual(),
                    capability=GuidedCapability.MANUAL,
                )
            )
            return

        if (
            form._field_present("choice_core_boot_classic_encrypted")
            and form.choice_core_boot_classic_encrypted.value
        ):
            self.controller.guided_choice(
                GuidedChoiceV2(
                    target=target, capability=GuidedCapability.CORE_BOOT_ENCRYPTED
                )
            )
            return

        if (
            form._field_present("choice_core_boot_classic_unencrypted")
            and form.choice_core_boot_classic_unencrypted.value
        ):
            self.controller.guided_choice(
                GuidedChoiceV2(
                    target=target, capability=GuidedCapability.CORE_BOOT_UNENCRYPTED
                )
            )
            return

        if form._field_present("choice_lvm") and form.choice_lvm.value:
            self.controller.guided_lvm(target, self.form.disk_by_id)
            return

        # choice_direct
        if GuidedCapability.DD in target.allowed:
            capability = GuidedCapability.DD
        else:
            capability = GuidedCapability.DIRECT
        self.controller.guided_choice(
            GuidedChoiceV2(target=target, capability=capability)
        )

    def manual(self, sender):
        self.controller.guided_choice(
            GuidedChoiceV2(
                target=GuidedStorageTargetManual(),
                capability=GuidedCapability.MANUAL,
            )
        )

    def refresh(self, sender):
        self.controller.guided()

    def cancel(self, btn=None):
        self.controller.cancel()


# ┌ LVM encryption ────────────────────────────────────────────────────┐
# │                                                                    │
# │  You chose to set up the LVM group on sda (500.000G).              │
# │  Encrypt the LVM group with LUKS?                                  │
# │                                                                    │
# │    ( )  Do not encrypt the LVM group                               │
# │    (X)  Encrypt the LVM group with LUKS                            │
# │                                                                    │
# │  Passphrase:         [ ********                  ]                 │
# │  Confirm passphrase: [ ********                  ]                 │
# │  [ ] Also create a recovery key                                    │
# │                                                                    │
# │                          [ Done ]   [ Back ]                       │
# └────────────────────────────────────────────────────────────────────┘


encrypt_off_label = _("Do not encrypt the LVM group")
encrypt_on_label = _("Encrypt the LVM group with LUKS")


class GuidedLVMForm(Form):
    encrypt_group = []

    encrypt_off = RadioButtonField(encrypt_group, encrypt_off_label)
    encrypt_on = RadioButtonField(encrypt_group, encrypt_on_label)
    passphrase = PasswordField(_("Passphrase:"))
    confirm_passphrase = PasswordField(_("Confirm passphrase:"))
    recovery_key = BooleanField(
        _("Also create a recovery key"),
        help=_(
            "The key will be stored as"
            " ~/recovery-key.txt in the live system and will"
            " be copied to /var/log/installer/ in the target"
            " system."
        ),
    )

    cancel_label = _("Back")

    def __init__(self):
        super().__init__(initial={"encrypt_off": True})
        self.confirm_passphrase.use_as_confirmation(
            for_field=self.passphrase, desc=_("Passphrases")
        )
        connect_signal(self.encrypt_off.widget, "change", self._toggle_encrypt)
        connect_signal(self.encrypt_on.widget, "change", self._toggle_encrypt)
        self._toggle_encrypt(None, self.encrypt_on.value)

    def _toggle_encrypt(self, sender, val):
        # The 'change' signal fires before the radio's state is actually
        # updated, so self.encrypt_on.value may still reflect the old state
        # when this callback runs. Use val (the new state of the sender)
        # combined with which radio fired to determine the effective state.
        if sender is self.encrypt_on.widget:
            encrypt = val
        elif sender is self.encrypt_off.widget:
            encrypt = not val
        else:
            encrypt = self.encrypt_on.value
        self.passphrase.enabled = encrypt
        self.confirm_passphrase.enabled = encrypt
        self.recovery_key.enabled = encrypt
        # Re-run validation so the Done button reflects the new state. The form
        # framework only re-validates a field on change when it is already
        # in-error, so toggling encryption on wouldn't otherwise flag an empty
        # passphrase (and toggling off wouldn't clear a stale error).
        self.passphrase.validate()
        self.confirm_passphrase.validate()
        self.validated()

    def validate_passphrase(self):
        if self.encrypt_on.value and len(self.passphrase.value) < 1:
            return _("Passphrase must be set")

    def validate_confirm_passphrase(self):
        if (
            self.encrypt_on.value
            and self.passphrase.value != self.confirm_passphrase.value
        ):
            return _("Passphrases do not match")


class GuidedLVMView(BaseView):
    title = _("LVM encryption")

    def __init__(self, controller, target: GuidedStorageTargetReformat, disk_by_id):
        self.controller = controller
        self.target = target
        self.disk = disk_by_id[target.disk_id]
        self.form = GuidedLVMForm()

        connect_signal(self.form, "submit", self.done)
        connect_signal(self.form, "cancel", self.cancel)

        excerpt = _(
            "You chose to set up the LVM group on {disk_id} ({size}).\n"
            "Encrypt the LVM group with LUKS?"
        ).format(disk_id=self.disk.label, size=humanize_size(self.disk.size))

        super().__init__(self.form.as_screen(focus_buttons=False, excerpt=excerpt))

    def done(self, sender):
        form = self.form
        if form.encrypt_on.value:
            recovery_key: Optional[RecoveryKey] = None
            if form.recovery_key.value:
                recovery_key = RecoveryKey(
                    live_location=str(pathlib.Path("~/recovery-key.txt").expanduser()),
                    backup_location="var/log/installer/recovery-key.txt",
                )
            choice = GuidedChoiceV2(
                target=self.target,
                capability=GuidedCapability.LVM_LUKS,
                password=form.passphrase.value,
                recovery_key=recovery_key,
            )
        else:
            choice = GuidedChoiceV2(
                target=self.target,
                capability=GuidedCapability.LVM,
            )
        self.controller.guided_choice(choice)

    def cancel(self, btn=None):
        self.controller.cancel()
