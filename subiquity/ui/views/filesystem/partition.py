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

"""Filesystem

Provides storage device selection and additional storage
configuration.

"""
import itertools
import logging
import re
from typing import Optional

from urwid import Text, connect_signal

from subiquity.common.filesystem import boot, gaps, labels
from subiquity.models.filesystem import (
    HUMAN_UNITS,
    LVM_CHUNK_SIZE,
    LVM_VolGroup,
    align_up,
    dehumanize_size,
    humanize_size,
)
from subiquity.ui.mount import MountField
from subiquity.ui.views.filesystem.format import (
    FormatForm,
    FSTypeField,
    initial_data_for_fs,
)
from subiquitycore.ui.container import Pile
from subiquitycore.ui.form import (
    BooleanField,
    FormField,
    WantsToKnowFormField,
    simple_field,
)
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.selector import Option
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import rewrap

log = logging.getLogger("subiquity.ui.views.filesystem.partition")


class SizeWidget(StringEditor):
    def __init__(self, form):
        self.form = form
        self.accurate_value: Optional[int] = None
        super().__init__()

    def lost_focus(self):
        val = self.value
        if not val:
            return
        suffixes = "".join(HUMAN_UNITS) + "".join(HUMAN_UNITS).lower()
        if val[-1] not in suffixes:
            unit = self.form.size_str[-1]
            val += unit
            self.value = val
        try:
            sz = self.form.size.value
        except ValueError:
            return
        if sz > self.form.max_size:
            self.value = self.form.size_str
            self.form.size.show_extra(
                (
                    "info_minor",
                    _("Capped partition size at {size}").format(
                        size=self.form.size_str
                    ),
                )
            )
            # This will invoke self.form.clean_size() and it is expected that
            # size_str (and therefore self.value) are properly aligned.
            self.accurate_value = self.form.size.value
        else:
            aligned_sz = align_up(sz, self.form.alignment)
            aligned_sz_str = humanize_size(aligned_sz)
            if aligned_sz != sz and aligned_sz_str != self.form.size.value:
                self.value = aligned_sz_str
                self.form.size.show_extra(
                    (
                        "info_minor",
                        _("Rounded size up to {size}").format(size=aligned_sz_str),
                    )
                )
            self.accurate_value = aligned_sz


class SizeField(FormField):
    def _make_widget(self, form):
        return SizeWidget(form)


class LVNameEditor(StringEditor, WantsToKnowFormField):
    def __init__(self):
        self.valid_char_pat = r"[-a-zA-Z0-9_+.]"
        self.error_invalid_char = _(
            "The only characters permitted in the "
            "name of a logical volume are a-z, A-Z, "
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


LVNameField = simple_field(LVNameEditor)


class PartitionForm(FormatForm):
    """Form for adding or editing a partition (or LVM logical volume).

    Extends FormatForm with name and size fields.
    """

    def __init__(
        self,
        model,
        max_size,
        initial,
        lvm_names,
        device,
        alignment,
        remote_storage: bool,
    ):
        self.max_size = max_size
        self.lvm_names = lvm_names
        self.alignment = alignment
        if max_size is not None:
            self.size_str = humanize_size(max_size)
            self.size.caption = _("Size (max {size}):").format(size=self.size_str)
        super().__init__(model, initial, device, remote_storage)
        if max_size is None:
            self.remove_field("size")

    # Fields are re-declared here (in display order) because MetaForm only
    # collects fields defined directly on each class, not inherited ones.
    name = LVNameField(_("Name: "))
    size = SizeField()
    fstype = FSTypeField(_("Format:"))
    mount = MountField(_("Mount:"))
    use_swap = BooleanField(
        _("Use as swap"), help=_("Use this swap partition in the installed system.")
    )

    def clean_size(self, val):
        if not val:
            return self.max_size
        suffixes = "".join(HUMAN_UNITS) + "".join(HUMAN_UNITS).lower()
        if val[-1] not in suffixes:
            val += self.size_str[-1]
        if val == self.size_str:
            return self.max_size
        else:
            return dehumanize_size(val)

    def validate_name(self):
        if self.lvm_names is None:
            return None
        v = self.name.value
        if not v:
            return _("The name of a logical volume cannot be empty")
        if v.startswith("-"):
            return _("The name of a logical volume cannot start with a hyphen")
        if v in (".", "..", "snapshot", "pvmove"):
            return _("A logical volume may not be called {name}").format(name=v)
        for substring in [
            "_cdata",
            "_cmeta",
            "_corig",
            "_mlog",
            "_mimage",
            "_pmspare",
            "_rimage",
            "_rmeta",
            "_tdata",
            "_tmeta",
            "_vorigin",
        ]:
            if substring in v:
                return _(
                    'The name of a logical volume may not contain "{substring}"'
                ).format(substring=substring)
        if v in self.lvm_names:
            return _("There is already a logical volume named {name}.").format(
                name=self.name.value
            )


bios_grub_partition_description = _(
    """\
Bootloader partition

{middle}

However, on a disk with a GPT partition table, there is not enough
space after the MBR for GRUB to store its second-stage core.img, so a
small unformatted partition is needed at the start of the disk. It
will not contain a filesystem and will not be mounted, and cannot be
edited here.
"""
)

unconfigured_bios_grub_partition_middle = _(
    """\
If this disk is selected as a boot device, GRUB will be installed onto
the target disk's MBR."""
)

configured_bios_grub_partition_middle = _(
    """\
As this disk has been selected as a boot device, GRUB will be
installed onto the target disk's MBR."""
)

unconfigured_boot_partition_description = _(
    """\
Bootloader partition

This is an ESP / "EFI system partition" as required by UEFI. If this
disk is selected as a boot device, Grub will be installed onto this
partition, which must be formatted as fat32.
"""
)

configured_boot_partition_description = _(
    """\
Bootloader partition

This is an ESP / "EFI system partition" as required by UEFI. As this
disk has been selected as a boot device, Grub will be installed onto
this partition, which must be formatted as fat32.
"""
)

boot_partition_description_size = _(
    """\
The only aspect of this partition that can be edited is the size.
"""
)

boot_partition_description_reformat = _(
    """\
You can choose whether to use the existing filesystem on this
partition or reformat it.
"""
)

unconfigured_prep_partition_description = _(
    """\
Required bootloader partition

This is the PReP partition which is required on POWER. If this disk is
selected as a boot device, Grub will be installed onto this partition.
"""
)

configured_prep_partition_description = _(
    """\
Required bootloader partition

This is the PReP partition which is required on POWER. As this disk has
been selected as a boot device, Grub will be installed onto this
partition.
"""
)


class PartitionStretchy(Stretchy):
    def __init__(self, parent, disk, *, partition=None, gap=None):
        self.disk = disk
        self.partition = partition
        self.gap = gap
        self.model = parent.model
        self.controller = parent.controller
        self.parent = parent

        if partition is None and gap is None:
            raise Exception("bad PartitionStretchy - needs partition or gap")

        initial = {}
        label = _("Create")
        if isinstance(disk, LVM_VolGroup):
            alignment = LVM_CHUNK_SIZE
            lvm_names = {p.name for p in disk.partitions()}
        else:
            alignment = disk.alignment_data().part_align
            lvm_names = None
        if partition:
            if partition.flag in ["bios_grub", "prep"]:
                label = None
                initial["mount"] = None
            elif boot.is_esp(partition) and not partition.grub_device:
                label = None
            else:
                label = _("Save")
            initial["size"] = humanize_size(self.partition.size)
            max_size = (
                partition.size
                + gaps.movable_trailing_partitions_and_gap_size(partition)[1]
            )

            if not boot.is_esp(partition):
                initial.update(initial_data_for_fs(self.partition.fs()))
            else:
                if partition.fs() and partition.fs().mount():
                    initial["mount"] = "/boot/efi"
                else:
                    initial["mount"] = None
            if isinstance(disk, LVM_VolGroup):
                initial["name"] = partition.name
                lvm_names.remove(partition.name)
            remote_storage = partition.on_remote_storage()
        else:
            initial["fstype"] = "ext4"
            max_size = self.gap.size
            if isinstance(disk, LVM_VolGroup):
                for x in itertools.count(start=0):
                    name = "lv-{}".format(x)
                    if name not in lvm_names:
                        break
                initial["name"] = name
            remote_storage = disk.on_remote_storage()

        self.form = PartitionForm(
            self.model,
            max_size,
            initial,
            lvm_names,
            partition,
            alignment,
            remote_storage,
        )

        if not isinstance(disk, LVM_VolGroup):
            self.form.remove_field("name")

        if label is not None:
            self.form.buttons.base_widget[0].set_label(label)
        else:
            del self.form.buttons.base_widget.contents[0]
            self.form.buttons.base_widget[0].set_label(_("OK"))

        if partition is not None:
            if boot.is_esp(partition):
                if partition.original_fstype():
                    opts = [
                        Option((_("Use existing fat32 filesystem"), True, None)),
                        Option(("---", False)),
                        Option(
                            (_("Reformat as fresh fat32 filesystem"), True, "fat32")
                        ),
                    ]
                    self.form.fstype.widget.options = opts
                    if partition.fs().preserve:
                        self.form.fstype.widget.index = 0
                    else:
                        self.form.fstype.widget.index = 2
                    if not self.partition.grub_device:
                        self.form.fstype.enabled = False
                    self.form.mount.enabled = False
                else:
                    opts = [Option(("fat32", True))]
                    self.form.fstype.widget.options = opts
                    self.form.fstype.widget.index = 0
                    self.form.mount.enabled = False
                    self.form.fstype.enabled = False
            elif partition.flag in ["bios_grub", "prep"]:
                self.form.mount.enabled = False
                self.form.fstype.enabled = False
                self.form.size.enabled = False
            if partition.preserve:
                self.form.name.enabled = False
                self.form.size.enabled = False

        connect_signal(self.form, "submit", self.done)
        connect_signal(self.form, "cancel", self.cancel)

        rows = []
        focus_index = 0
        if partition is not None:
            if boot.is_esp(self.partition):
                if self.partition.grub_device:
                    desc = _(configured_boot_partition_description)
                    if self.partition.preserve:
                        desc += _(boot_partition_description_reformat)
                    else:
                        desc += _(boot_partition_description_size)
                else:
                    focus_index = 2
                    desc = _(unconfigured_boot_partition_description)
                rows.extend(
                    [
                        Text(rewrap(desc)),
                        Text(""),
                    ]
                )
            elif self.partition.flag == "bios_grub":
                if self.partition.device.grub_device:
                    middle = _(configured_bios_grub_partition_middle)
                else:
                    middle = _(unconfigured_bios_grub_partition_middle)
                desc = _(bios_grub_partition_description).format(middle=middle)
                rows.extend(
                    [
                        Text(rewrap(desc)),
                        Text(""),
                    ]
                )
                focus_index = 2
            elif self.partition.flag == "prep":
                if self.partition.grub_device:
                    desc = _(configured_prep_partition_description)
                else:
                    desc = _(unconfigured_prep_partition_description)
                rows.extend(
                    [
                        Text(rewrap(desc)),
                        Text(""),
                    ]
                )
                focus_index = 2
        rows.extend(self.form.as_rows())
        self.form.form_pile = Pile(rows)
        widgets = [
            self.form.form_pile,
            Text(""),
            self.form.buttons,
        ]

        if partition is None:
            if isinstance(disk, LVM_VolGroup):
                title = _("Adding logical volume to {vgname}").format(
                    vgname=labels.label(disk)
                )
            else:
                title = _("Adding {ptype} partition to {device}").format(
                    ptype=disk.ptable_for_new_partition().upper(),
                    device=labels.label(disk),
                )
        else:
            if isinstance(disk, LVM_VolGroup):
                title = _("Editing logical volume {lvname} of {vgname}").format(
                    lvname=partition.name, vgname=labels.label(disk)
                )
            else:
                title = _("Editing partition {number} of {device}").format(
                    number=partition.number, device=labels.label(disk)
                )

        super().__init__(title, widgets, 0, focus_index)

    def cancel(self, button=None):
        self.parent.remove_overlay()

    def done(self, form):
        log.debug("Add Partition Result: {}".format(form.as_data()))
        spec = form.as_data()
        if self.partition is not None and boot.is_esp(self.partition):
            if self.partition.original_fstype() is None:
                spec["fstype"] = self.partition.fs().fstype
            if self.partition.fs().mount() is not None:
                spec["mount"] = self.partition.fs().mount().path
            else:
                spec["mount"] = None
        if isinstance(self.disk, LVM_VolGroup):
            handler = self.controller.logical_volume_handler
        else:
            handler = self.controller.partition_disk_handler
        handler(self.disk, spec, partition=self.partition, gap=self.gap)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()
