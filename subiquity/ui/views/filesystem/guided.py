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

import attr
from urwid import Text, connect_signal

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
    SizingPolicy,
)
from subiquity.common.filesystem.sizes import get_bootfs_size
from subiquity.models.filesystem import (
    GiB,
    MiB,
    align_up,
    dehumanize_size,
    humanize_size,
)
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
    SubForm,
    SubFormField,
)
from subiquitycore.ui.selector import Option
from subiquitycore.ui.table import TablePile, TableRow
from subiquitycore.ui.utils import Color, rewrap, screen
from subiquitycore.view import BaseView
from subiquity.ui.views.filesystem.partition import SizeField

log = logging.getLogger("subiquity.ui.views.filesystem.guided")

subtitle = _("Configure a guided storage layout, or create a custom one:")


class LUKSOptionsForm(SubForm):
    passphrase = PasswordField(_("Passphrase:"))
    confirm_passphrase = PasswordField(_("Confirm passphrase:"))
    recovery_key = BooleanField(
        ("Also create a recovery key"),
        help=_(
            "The key will be stored as"
            " ~/recovery-key.txt in the live system and will"
            " be copied to /var/log/installer/ in the target"
            " system."
        ),
    )

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
            self.use_tpm.enabled = False
            core_boot_disallowed = [
                d for d in val.disallowed if d.capability.is_core_boot()
            ]
            if core_boot_disallowed:
                self.use_tpm.help = core_boot_disallowed[0].message
            else:
                self.use_tpm.help = ""

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


class GuidedDiskSelectionViewV2Debug(BaseView):
    title = "Guided storage configuration for storage version 2 (only for debugging)"

    desc = """
/!\\ This view is only for debugging. Its goal is to make it easier to reproduce \
some storage-version=2 bugs that may have occurred using the desktop installer.

Considerations:
 * The view is incomplete, has no translations, might crash in some scenarios, use \
it at your own risk...
 * The allowed / disallowed capabilities are basically ignored. Selecting \
a scenario will use the DIRECT capability (except for manual partitioning where \
it will use MANUAL)
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
            # Feel free to implement something more than DIRECT
            self.controller.guided_choice(
                GuidedChoiceV2(target=target, capability=GuidedCapability.DIRECT)
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
        results = self.form.as_data()
        if results["guided"]:
            guided_choice = results["guided_choice"]
            target = guided_choice["disk"]
            tpm_choice = self.form.guided_choice.widget.form.tpm_choice
            password = None
            recovery_key: Optional[RecoveryKey] = None
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
                    if opts["luks_options"]["recovery_key"]:
                        # There is only one encrypted LUKS (at max) in guided
                        # so no need to prefix the locations with the name of
                        # the VG.
                        recovery_key = RecoveryKey(
                            live_location=str(
                                pathlib.Path("~/recovery-key.txt").expanduser()
                            ),
                            backup_location="var/log/installer/recovery-key.txt",
                        )
                else:
                    capability = GuidedCapability.LVM
            else:
                if GuidedCapability.DD in target.allowed:
                    capability = GuidedCapability.DD
                else:
                    capability = GuidedCapability.DIRECT
            choice = GuidedChoiceV2(
                target=target,
                capability=capability,
                password=password,
                recovery_key=recovery_key,
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

    def refresh(self, sender):
        self.controller.guided()

    def cancel(self, btn=None):
        self.controller.cancel()


# =============================================================================
# Akash HomeNode Storage Configuration View
# =============================================================================

# Minimum storage requirement for Akash HomeNode (in bytes)
HOMENODE_MIN_SIZE = 100 * GiB

# Estimated overhead for /boot partition created by guided_lvm()
# (the ESP is reused from the existing disk when installing alongside)
BOOT_OVERHEAD = 2 * GiB


class HomenodeStorageForm(Form):
    """Simple 3-option form for Akash HomeNode storage configuration.

    Options:
        1. Use entire disk - wipe and use all space
        2. Install alongside existing OS - resize largest partition
        3. Custom storage layout - manual partitioning
    """

    group = []

    use_entire_disk = RadioButtonField(
        group, _("Use entire disk"), help=NO_HELP
    )
    install_alongside = RadioButtonField(
        group, _("Install alongside existing OS"), help=NO_HELP
    )
    size = SizeField()
    custom = RadioButtonField(
        group, _("Custom storage layout"), help=NO_HELP
    )

    cancel_label = _("Back")

    def __init__(
        self,
        alignment,
        max_allocatable,
        resize_available,
    ):
        self.alignment = alignment
        self.max_size = max_allocatable
        self.min_homenode_size = align_up(HOMENODE_MIN_SIZE, alignment)

        if max_allocatable > 0:
            self.size_str = humanize_size(max_allocatable)
        else:
            self.size_str = humanize_size(self.min_homenode_size)

        initial = {
            "size": humanize_size(self.min_homenode_size),
        }

        self.size.caption = _(
            "Allocate to Akash HomeNode (min {min}, max {max}):"
        ).format(
            min=humanize_size(self.min_homenode_size),
            max=humanize_size(max_allocatable) if max_allocatable > 0 else "N/A",
        )

        super().__init__(initial)

        # Wire up radio button toggles
        connect_signal(
            self.use_entire_disk.widget, "change", self._toggle_option
        )
        connect_signal(
            self.install_alongside.widget, "change", self._toggle_option
        )
        connect_signal(self.custom.widget, "change", self._toggle_option)

        # If resize is not available, disable the option
        if not resize_available:
            self.install_alongside.enabled = False
            self.size.enabled = False
        else:
            # Size field is only active when "install alongside" is selected
            self.size.enabled = False

    def _toggle_option(self, sender, new_value):
        """Show/hide the size field based on which radio button is selected."""
        if self.install_alongside.widget.state and self.install_alongside.enabled:
            self.size.enabled = True
        else:
            self.size.enabled = False
        self.validated()

    def clean_size(self, val):
        if not val:
            return self.min_homenode_size
        suffixes = "BKMGTP" + "bkmgtp"
        if val[-1] not in suffixes:
            unit = self.size_str[-1]
            val += unit
        if val == self.size_str:
            return self.max_size
        else:
            return dehumanize_size(val)

    def validate_size(self):
        if not self.install_alongside.widget.state:
            return None
        try:
            sz = self.size.value
        except ValueError:
            return _("Invalid size")
        aligned_sz = align_up(sz, self.alignment)
        if aligned_sz < self.min_homenode_size:
            return _("Akash HomeNode requires at least {size}").format(
                size=humanize_size(self.min_homenode_size)
            )
        if aligned_sz > self.max_size:
            return _("Cannot allocate more than {size}").format(
                size=humanize_size(self.max_size)
            )


class HomenodeStorageView(BaseView):
    """Akash HomeNode storage configuration screen.

    Presents three options:
        1. Use entire disk - wipe largest disk, LVM, use all space
        2. Install alongside - resize largest partition, LVM in freed space
        3. Custom - go to manual partition editor
    """

    title = _("Storage configuration")

    def __init__(self, controller, targets, disk_by_id):
        self.controller = controller

        # --- Find the best reformat target (largest disk) ---
        self.reformat_target = None
        reformat_disk_size = 0
        for target in targets:
            if not isinstance(target, GuidedStorageTargetReformat):
                continue
            if not target.allowed:
                continue
            disk = disk_by_id.get(target.disk_id)
            if disk is None:
                continue
            if disk.has_in_use_partition:
                continue
            if disk.size > reformat_disk_size:
                reformat_disk_size = disk.size
                self.reformat_target = target

        # Get the disk object for display
        self.target_disk = None
        if self.reformat_target is not None:
            self.target_disk = disk_by_id.get(self.reformat_target.disk_id)

        # --- Find the best resize target (on the same disk) ---
        self.resize_target = None
        self.resize_partition = None
        resize_install_max = 0
        for target in targets:
            if not isinstance(target, GuidedStorageTargetResize):
                continue
            if not target.allowed:
                continue
            # Prefer resize on the same disk as the wipe target
            if (
                self.reformat_target is not None
                and target.disk_id != self.reformat_target.disk_id
            ):
                continue
            disk = disk_by_id.get(target.disk_id)
            if disk is None:
                continue
            # Find the partition being resized
            partition = None
            for p in disk.partitions:
                if isinstance(p, Partition) and p.number == target.partition_number:
                    partition = p
                    break
            if partition is None:
                continue
            # Calculate how much we can free
            max_free = partition.size - target.minimum
            if max_free < HOMENODE_MIN_SIZE + BOOT_OVERHEAD:
                continue
            if max_free > resize_install_max:
                resize_install_max = max_free
                self.resize_target = target
                self.resize_partition = partition

        # --- Calculate size constraints for the resize option ---
        resize_available = self.resize_target is not None
        alignment = MiB  # default partition alignment
        max_allocatable = 0

        if resize_available and self.resize_partition is not None:
            # Max we can free = partition_size - minimum_partition_size
            max_free = self.resize_partition.size - self.resize_target.minimum
            # Subtract boot overhead (guided_lvm creates /boot in the gap)
            max_allocatable = max_free - BOOT_OVERHEAD
            max_allocatable = max(0, max_allocatable)
            if max_allocatable < HOMENODE_MIN_SIZE:
                resize_available = False
                max_allocatable = 0

        # --- Build the form ---
        self.form = HomenodeStorageForm(
            alignment=alignment,
            max_allocatable=max_allocatable,
            resize_available=resize_available,
        )

        # -- Option 1: Use entire disk --
        if self.target_disk is not None:
            devpath = self.target_disk.path or self.target_disk.label
            self.form.use_entire_disk.help = _(
                "Erase all data on {dev} and use the full {size} "
                "for Akash HomeNode."
            ).format(dev=devpath, size=humanize_size(self.target_disk.size))

        # -- Option 2: Install alongside --
        if resize_available and self.resize_partition is not None:
            part_desc = "partition {}".format(self.resize_partition.number)
            if self.resize_partition.os:
                part_desc = str(self.resize_partition.os)
            part_fmt = self.resize_partition.format or "unknown"
            self.form.install_alongside.help = _(
                "Shrink {part} ({fmt}, {size}) and create a new "
                "partition for Akash HomeNode.\n"
                "The existing OS and its data will be preserved."
            ).format(
                part=part_desc,
                fmt=part_fmt,
                size=humanize_size(self.resize_partition.size),
            )
        else:
            self.form.install_alongside.help = _(
                "Not available - no resizable partition with enough "
                "free space was found."
            )

        # -- Option 3: Custom --
        self.form.custom.help = _(
            "Manually configure partitions, LVM, and mount points."
        )

        # --- Wire up form signals ---
        connect_signal(self.form, "submit", self.done)
        connect_signal(self.form, "cancel", self.cancel)

        # --- Build the excerpt text ---
        excerpt_parts = []
        if self.target_disk is not None:
            disk_desc = self.target_disk.label
            if self.target_disk.model:
                disk_desc = self.target_disk.model
            if self.target_disk.path:
                disk_desc += " [{}]".format(self.target_disk.path)
            excerpt_parts.append(
                "Akash HomeNode requires at least 100 GB of storage.\n"
                "Largest disk: {desc} ({size})".format(
                    desc=disk_desc,
                    size=humanize_size(self.target_disk.size),
                )
            )
        else:
            excerpt_parts.append(
                "No suitable disk found for installation."
            )

        excerpt_text = "\n".join(excerpt_parts)

        super().__init__(
            self.form.as_screen(
                focus_buttons=False,
                excerpt=excerpt_text,
            )
        )

    def done(self, sender):
        data = self.form.as_data()

        if data.get("use_entire_disk"):
            if self.reformat_target is None:
                return
            choice = GuidedChoiceV2(
                target=self.reformat_target,
                capability=GuidedCapability.LVM,
                sizing_policy=SizingPolicy.ALL,
            )

        elif data.get("install_alongside"):
            if self.resize_target is None:
                return
            # Calculate new_size for the existing partition
            try:
                user_size = self.form.size.value
            except ValueError:
                return
            user_size = align_up(user_size, self.form.alignment)

            # The freed space needs to fit: user_size + boot overhead
            freed_needed = user_size + BOOT_OVERHEAD
            new_size = self.resize_partition.size - freed_needed
            new_size = align_up(new_size, self.form.alignment)

            # Clamp to valid range
            new_size = max(new_size, self.resize_target.minimum)
            new_size = min(new_size, self.resize_target.maximum)

            self.resize_target.new_size = new_size
            choice = GuidedChoiceV2(
                target=self.resize_target,
                capability=GuidedCapability.LVM,
                sizing_policy=SizingPolicy.ALL,
            )

        else:
            # Custom storage layout
            choice = GuidedChoiceV2(
                target=GuidedStorageTargetManual(),
                capability=GuidedCapability.MANUAL,
            )

        self.controller.guided_choice(choice)

    def cancel(self, btn=None):
        self.controller.cancel()
