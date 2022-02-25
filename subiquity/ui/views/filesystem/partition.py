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

""" Filesystem

Provides storage device selection and additional storage
configuration.

"""
import logging
import re

from urwid import connect_signal, Text

from subiquitycore.ui.form import (
    BooleanField,
    Form,
    FormField,
    simple_field,
    WantsToKnowFormField,
)
from subiquitycore.ui.interactive import StringEditor
from subiquitycore.ui.selector import Option, Selector
from subiquitycore.ui.container import Pile
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import rewrap

from subiquity.common.filesystem import boot, gaps, labels
from subiquity.models.filesystem import (
    align_up,
    Disk,
    HUMAN_UNITS,
    dehumanize_size,
    humanize_size,
    LVM_CHUNK_SIZE,
    LVM_VolGroup,
)
from subiquity.ui.mount import (
    common_mountpoints,
    MountField,
    suitable_mountpoints_for_existing_fs,
    )


log = logging.getLogger('subiquity.ui.views.filesystem.partition')


DEFAULT_ALIGNMENT = 1 << 20


class FSTypeField(FormField):

    takes_default_style = False

    def _make_widget(self, form):
        # This will need to do something different for editing an
        # existing partition that is already formatted.
        options = [
            ('ext4',  True),
            ('xfs',   True),
            ('btrfs', True),
            ('---',   False),
            ('swap',  True),
        ]
        if form.existing_fs_type is None:
            options = options + [
                ('---',                  False),
                (_('Leave unformatted'), True, None),
                ]
        else:
            label = _('Leave formatted as {fstype}').format(
                fstype=form.existing_fs_type)
            options = [
                (label, True, None),
                ('---', False),
                ] + options
        sel = Selector(opts=options)
        sel.value = None
        return sel


class SizeWidget(StringEditor):
    def __init__(self, form):
        self.form = form
        super().__init__()

    def lost_focus(self):
        val = self.value
        if not val:
            return
        suffixes = ''.join(HUMAN_UNITS) + ''.join(HUMAN_UNITS).lower()
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
                ('info_minor',
                 _("Capped partition size at {size}").format(
                     size=self.form.size_str)))
        else:
            aligned_sz = align_up(sz, self.form.alignment)
            aligned_sz_str = humanize_size(aligned_sz)
            if aligned_sz != sz and aligned_sz_str != self.form.size.value:
                self.value = aligned_sz_str
                self.form.size.show_extra(
                    ('info_minor', _("Rounded size up to {size}").format(
                        size=aligned_sz_str)))


class SizeField(FormField):
    def _make_widget(self, form):
        return SizeWidget(form)


class LVNameEditor(StringEditor, WantsToKnowFormField):
    def __init__(self):
        self.valid_char_pat = r'[-a-zA-Z0-9_+.]'
        self.error_invalid_char = _("The only characters permitted in the "
                                    "name of a logical volume are a-z, A-Z, "
                                    "0-9, +, _, . and -")
        super().__init__()

    def valid_char(self, ch):
        if len(ch) == 1 and not re.match(self.valid_char_pat, ch):
            self.bff.in_error = True
            self.bff.show_extra(("info_error", self.error_invalid_char))
            return False
        else:
            return super().valid_char(ch)


LVNameField = simple_field(LVNameEditor)


class PartitionForm(Form):

    def __init__(self, model, max_size, initial, lvm_names, device, alignment):
        self.model = model
        self.device = device
        self.existing_fs_type = None
        if device:
            ofstype = device.original_fstype()
            if ofstype:
                self.existing_fs_type = ofstype
        initial_path = initial.get('mount')
        self.mountpoints = {
            m.path: m.device.volume for m in self.model.all_mounts()
            if m.path != initial_path}
        self.max_size = max_size
        if max_size is not None:
            self.size_str = humanize_size(max_size)
            self.size.caption = _("Size (max {size}):").format(
                size=self.size_str)
        self.lvm_names = lvm_names
        self.alignment = alignment
        super().__init__(initial)
        if max_size is None:
            self.remove_field('size')
        connect_signal(self.fstype.widget, 'select', self.select_fstype)
        self.form_pile = None
        self.select_fstype(None, self.fstype.widget.value)

    def select_fstype(self, sender, fstype):
        show_use = False
        if fstype is None and self.existing_fs_type is not None:
            self.mount.widget.disable_unsuitable_mountpoints_for_existing_fs()
            self.mount.value = self.mount.value
        else:
            self.mount.widget.enable_common_mountpoints()
            self.mount.value = self.mount.value
        if fstype is None:
            if self.existing_fs_type == "swap":
                show_use = True
        if self.form_pile is not None:
            for i, (w, o) in enumerate(self.form_pile.contents):
                if w is self.mount._table and show_use:
                    self.form_pile.contents[i] = (self.use_swap._table, o)
                elif w is self.use_swap._table and not show_use:
                    self.form_pile.contents[i] = (self.mount._table, o)
        if not boot.is_esp(self.device):
            fstype_for_check = fstype
            if fstype_for_check is None:
                fstype_for_check = self.existing_fs_type
            self.mount.enabled = self.model.is_mounted_filesystem(
                fstype_for_check)
        self.fstype.value = fstype
        self.mount.showing_extra = False
        self.mount.validate()

    name = LVNameField(_("Name: "))
    size = SizeField()
    fstype = FSTypeField(_("Format:"))
    mount = MountField(_("Mount:"))
    use_swap = BooleanField(
        _("Use as swap"),
        help=_("Use this swap partition in the installed system."))

    def clean_size(self, val):
        if not val:
            return self.max_size
        suffixes = ''.join(HUMAN_UNITS) + ''.join(HUMAN_UNITS).lower()
        if val[-1] not in suffixes:
            val += self.size_str[-1]
        if val == self.size_str:
            return self.max_size
        else:
            return dehumanize_size(val)

    def clean_mount(self, val):
        if self.model.is_mounted_filesystem(self.fstype):
            return val
        else:
            return None

    def validate_name(self):
        if self.lvm_names is None:
            return None
        v = self.name.value
        if not v:
            return _("The name of a logical volume cannot be empty")
        if v.startswith('-'):
            return _("The name of a logical volume cannot start with a hyphen")
        if v in ('.', '..', 'snapshot', 'pvmove'):
            return _(
                "A logical volume may not be called {name}"
                ).format(name=v)
        for substring in ['_cdata', '_cmeta',   '_corig',  '_mlog',  '_mimage',
                          '_pmspare',  '_rimage',  '_rmeta',  '_tdata',
                          '_tmeta', '_vorigin']:
            if substring in v:
                return _(
                    'The name of a logical volume may not contain '
                    '"{substring}"'
                    ).format(substring=substring)
        if v in self.lvm_names:
            return _(
                "There is already a logical volume named {name}."
                ).format(name=self.name.value)

    def validate_mount(self):
        mount = self.mount.value
        if mount is None:
            return
        # /usr/include/linux/limits.h:PATH_MAX
        if len(mount) > 4095:
            return _('Path exceeds PATH_MAX')
        dev = self.mountpoints.get(mount)
        if dev is not None:
            return _("{device} is already mounted at {path}.").format(
                device=labels.label(dev).title(), path=mount)
        if self.existing_fs_type is not None:
            if self.fstype.value is None:
                if mount in common_mountpoints:
                    if mount not in suitable_mountpoints_for_existing_fs:
                        self.mount.show_extra(
                            ('info_error',
                             _("Mounting an existing filesystem at "
                               "{mountpoint} is usually a bad idea, "
                               "proceed only with caution.").format(
                                   mountpoint=mount)))

    def as_rows(self):
        r = super().as_rows()
        if self.existing_fs_type == "swap":
            exclude = self.mount._table
        else:
            exclude = self.use_swap._table
        i = r.index(exclude)
        del r[i-1:i+1]
        return r


bios_grub_partition_description = _("""\
Bootloader partition

{middle}

However, on a disk with a GPT partition table, there is not enough
space after the MBR for GRUB to store its second-stage core.img, so a
small unformatted partition is needed at the start of the disk. It
will not contain a filesystem and will not be mounted, and cannot be
edited here.
""")

unconfigured_bios_grub_partition_middle = _("""\
If this disk is selected as a boot device, GRUB will be installed onto
the target disk's MBR.""")

configured_bios_grub_partition_middle = _("""\
As this disk has been selected as a boot device, GRUB will be
installed onto the target disk's MBR.""")

unconfigured_boot_partition_description = _("""\
Bootloader partition

This is an ESP / "EFI system partition" as required by UEFI. If this
disk is selected as a boot device, Grub will be installed onto this
partition, which must be formatted as fat32.
""")

configured_boot_partition_description = _("""\
Bootloader partition

This is an ESP / "EFI system partition" as required by UEFI. As this
disk has been selected as a boot device, Grub will be installed onto
this partition, which must be formatted as fat32.
""")

boot_partition_description_size = _("""\
The only aspect of this partition that can be edited is the size.
""")

boot_partition_description_reformat = _("""\
You can choose whether to use the existing filesystem on this
partition or reformat it.
""")

unconfigured_prep_partition_description = _("""\
Required bootloader partition

This is the PReP partion which is required on POWER. If this disk is
selected as a boot device, Grub will be installed onto this partition.
""")

configured_prep_partition_description = _("""\
Required bootloader partition

This is the PReP partion which is required on POWER. As this disk has
been selected as a boot device, Grub will be installed onto this
partition.
""")


def initial_data_for_fs(fs):
    r = {}
    if fs is not None:
        if fs.preserve:
            r['fstype'] = None
            if fs.fstype == "swap":
                r['use_swap'] = fs.mount() is not None
        else:
            r['fstype'] = fs.fstype
        if fs._m.is_mounted_filesystem(fs.fstype):
            mount = fs.mount()
            if mount is not None:
                r['mount'] = mount.path
            else:
                r['mount'] = None
    return r


class PartitionStretchy(Stretchy):

    def __init__(self, parent, disk, partition=None):
        self.disk = disk
        self.partition = partition
        self.model = parent.model
        self.controller = parent.controller
        self.parent = parent
        max_size = gaps.largest_gap_size(disk)

        initial = {}
        label = _("Create")
        if isinstance(disk, LVM_VolGroup):
            alignment = LVM_CHUNK_SIZE
            lvm_names = {p.name for p in disk.partitions()}
        else:
            alignment = DEFAULT_ALIGNMENT
            lvm_names = None
        if self.partition:
            if partition.flag in ["bios_grub", "prep"]:
                label = None
                initial['mount'] = None
            elif boot.is_esp(partition) and not partition.grub_device:
                label = None
            else:
                label = _("Save")
            initial['size'] = humanize_size(self.partition.size)
            max_size += self.partition.size

            if not boot.is_esp(partition):
                initial.update(initial_data_for_fs(self.partition.fs()))
            else:
                if partition.fs() and partition.fs().mount():
                    initial['mount'] = '/boot/efi'
                else:
                    initial['mount'] = None
            if isinstance(disk, LVM_VolGroup):
                initial['name'] = partition.name
                lvm_names.remove(partition.name)
        else:
            initial['fstype'] = 'ext4'
            if isinstance(disk, LVM_VolGroup):
                x = 0
                while True:
                    name = 'lv-{}'.format(x)
                    if name not in lvm_names:
                        break
                    x += 1
                initial['name'] = name

        self.form = PartitionForm(
            self.model, max_size, initial, lvm_names, partition, alignment)

        if not isinstance(disk, LVM_VolGroup):
            self.form.remove_field('name')

        if label is not None:
            self.form.buttons.base_widget[0].set_label(label)
        else:
            del self.form.buttons.base_widget.contents[0]
            self.form.buttons.base_widget[0].set_label(_("OK"))

        if partition is not None:
            if boot.is_esp(partition):
                if partition.original_fstype():
                    opts = [
                        Option((
                            _("Use existing fat32 filesystem"),
                            True,
                            None
                            )),
                        Option(("---", False)),
                        Option((
                                _("Reformat as fresh fat32 filesystem"),
                                True,
                                "fat32"
                            )),
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

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

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
                rows.extend([
                    Text(rewrap(desc)),
                    Text(""),
                ])
            elif self.partition.flag == "bios_grub":
                if self.partition.device.grub_device:
                    middle = _(configured_bios_grub_partition_middle)
                else:
                    middle = _(unconfigured_bios_grub_partition_middle)
                desc = _(bios_grub_partition_description).format(middle=middle)
                rows.extend([
                    Text(rewrap(desc)),
                    Text(""),
                ])
                focus_index = 2
            elif self.partition.flag == "prep":
                if self.partition.grub_device:
                    desc = _(configured_prep_partition_description)
                else:
                    desc = _(unconfigured_prep_partition_description)
                rows.extend([
                    Text(rewrap(desc)),
                    Text(""),
                ])
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
                    vgname=labels.label(disk))
            else:
                title = _("Adding {ptype} partition to {device}").format(
                    ptype=disk.ptable_for_new_partition().upper(),
                    device=labels.label(disk))
        else:
            if isinstance(disk, LVM_VolGroup):
                title = _(
                    "Editing logical volume {lvname} of {vgname}"
                    ).format(
                        lvname=partition.name,
                        vgname=labels.label(disk))
            else:
                title = _("Editing partition {number} of {device}").format(
                    number=partition.number,
                    device=labels.label(disk))

        super().__init__(title, widgets, 0, focus_index)

    def cancel(self, button=None):
        self.parent.remove_overlay()

    def done(self, form):
        log.debug("Add Partition Result: {}".format(form.as_data()))
        data = form.as_data()
        if self.partition is not None and boot.is_esp(self.partition):
            if self.partition.original_fstype() is None:
                data['fstype'] = self.partition.fs().fstype
            if self.partition.fs().mount() is not None:
                data['mount'] = self.partition.fs().mount().path
            else:
                data['mount'] = None
        if isinstance(self.disk, LVM_VolGroup):
            handler = self.controller.logical_volume_handler
        else:
            handler = self.controller.partition_disk_handler
        handler(self.disk, self.partition, data)
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()


class FormatEntireStretchy(Stretchy):

    def __init__(self, parent, device):

        self.device = device
        self.model = parent.model
        self.controller = parent.controller
        self.parent = parent

        initial = {}
        fs = device.fs()
        if fs is not None:
            initial.update(initial_data_for_fs(fs))
        elif not isinstance(device, Disk):
            initial['fstype'] = 'ext4'
        self.form = PartitionForm(
            self.model, 0, initial, None, device, DEFAULT_ALIGNMENT)
        self.form.remove_field('size')
        self.form.remove_field('name')

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        rows = []
        if isinstance(device, Disk):
            rows = [
                Text(_("Formatting and mounting a disk directly is unusual. "
                       "You probably want to add a partition instead.")),
                Text(""),
                ]
        rows.extend(self.form.as_rows())
        self.form.form_pile = Pile(rows)
        widgets = [
            self.form.form_pile,
            Text(""),
            self.form.buttons,
        ]

        title = _("Format and/or mount {device}").format(
            device=labels.label(device))

        super().__init__(title, widgets, 0, 0)

    def cancel(self, button=None):
        self.parent.remove_overlay()

    def done(self, form):
        log.debug("Format Entire Result: {}".format(form.as_data()))
        self.controller.add_format_handler(self.device, form.as_data())
        self.parent.refresh_model_inputs()
        self.parent.remove_overlay()
